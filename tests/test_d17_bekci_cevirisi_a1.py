"""ÖH Dalga-17 / kulvar ``bekci-cevirisi`` aşama 1 — BEKÇİ KİLİTLERİ.

Bu dosya bir onarım dosyası değil, bir KİLİT dosyasıdır: Dalga-15 ve
Dalga-16'dan devralınan kalemlerin bugün ölçülen doğru davranışını, geri
gitmeyecek biçimde çiviler.

KİLİTLENEN KALEMLER
-------------------
``OH-Z5-16`` (Fable-D15 ŞART)
    Hazne basıncı üst sınırı bekçilerde İKİNCİ KEZ yazılmaz; deponun kanonik
    tablosundan (``MotorDataValidator().limits``) okunur — uç kapısının
    (``hrma/app.py::_ust_sinir_bandi``) okuduğu yerin ta kendisi.

``OH-D16-09`` (D16 devri)
    Sarsım aracının iki kör noktası. (A) Yankı-simetri kuralı bir dal
    anahtarının koca bir alt ağacı kaldırmasını "ayrışma" sanmamalı.
    (B) ``perturb`` taban değeri bilinmeyen ikili alanı TAHMİN ETMEMELİ.

``P10B4-06`` (D16 devri)
    Seçim alanı TEK alternatifle sarsılıyor. "Canlı" hükmü 1/N ölçümüne
    dayanıyorsa bu ADIYLA beyan edilmeli; kullanıcının açılır listede
    görebildiği kırık seçenekler görünmez kalmamalı.

ÖLÇÜM KAYITLARI
---------------
``docs/scofield/raw/OH/D17/bekci-cevirisi/a1/``: ``olcum_ohz515.py`` /
``olcum_ohz515b.py`` (+ ``once_*.json``), ``olcum_shake.py``
(``once_shake.json`` ⟷ ``sonra_shake.json``), ``olcum_ohz516.py``,
``mutasyon.py`` / ``mutasyon.json``.
"""

import ast
import json
import pathlib
import re

import pytest

from tests.support import inventory, shake
from tests.test_field_wiring_layer_b import HYBRID_BASE
from tests.support.kanit import kanit_gerekli


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


# ===========================================================================
# 1) OH-Z5-16 — BANDIN TAVANI TEK KAYNAKTAN OKUNUR
# ===========================================================================

class TestOHZ516BandTavaniTekKaynak:
    """Fable-D15 ŞART'ı: 500 bar iki bekçide daha YAZILMAZ, okunur.

    Kusurun biçimi: bekçi eşiği kendi içinde sabitlerse, depo tablosu
    değiştiğinde test kendi eski sayısını savunur ve "band" iddiası
    ürünle ilgisini keser. Doktrin 4 (tek kaynak) tam bunu yasaklar.
    """

    @staticmethod
    def _kanonik_tavan():
        from hrma.validation.motor_validation import MotorDataValidator
        return float(MotorDataValidator().limits['chamber_pressure']['max'])

    def test_dock_sozlesmesi_kanonik_tablodan_okur(self):
        from tests.test_analysis_dock_contract import (
            TestStructuralResponseContract as _Dock)
        assert float(_Dock.BAND_TAVANI_BAR) == self._kanonik_tavan()

    def test_civata_vakalari_kanonik_tablodan_okur(self):
        from tests.test_d15_bekci_cevirisi_a1 import (
            BAND_TAVANI_BAR, CIVATA_VAKALARI)
        assert float(BAND_TAVANI_BAR) == self._kanonik_tavan()
        tavan_satirlari = [pc for pc, _cap in CIVATA_VAKALARI
                           if float(pc) == float(BAND_TAVANI_BAR)]
        assert len(tavan_satirlari) >= 4, (
            'bandın tavanında ölçülen köşe kalmadı: '
            f'{CIVATA_VAKALARI}')

    def test_ucun_kapisi_ayni_tavani_uyguluyor(self, client):
        """İddia YAZIYLA değil UÇLA doğrulanır: tavan geçer, üstü 422."""
        from tests.test_analysis_dock_contract import STRUCTURAL_PAYLOAD
        tavan = self._kanonik_tavan()
        gecen = client.post('/analyze_structural_safety',
                            json=dict(STRUCTURAL_PAYLOAD,
                                      chamber_pressure=tavan,
                                      chamber_diameter=0.4))
        assert gecen.status_code == 200, (
            f'kanonik tavan {tavan} bar bandın İÇİNDE olmalıydı, '
            f'{gecen.status_code} döndü — bekçinin okuduğu tablo ile ucun '
            'uyguladığı kapı ayrışmış')
        asan = client.post('/analyze_structural_safety',
                           json=dict(STRUCTURAL_PAYLOAD,
                                     chamber_pressure=tavan + 1.0,
                                     chamber_diameter=0.4))
        assert asan.status_code == 422, (
            f'tavan + 1 bar ({tavan + 1.0}) {asan.status_code} döndü — '
            'üst sınır kapısı bu tabloyu okumuyor')

    def test_bekcilerde_ikinci_bir_tavan_sabiti_kalmadi(self):
        """Sayı YENİDEN YAZILMAZ; ikinci kaynak dosyada duruyorsa kırmızı."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent
        tavan = int(self._kanonik_tavan())
        for ad in ('test_analysis_dock_contract.py',
                   'test_d15_bekci_cevirisi_a1.py'):
            metin = (kok / ad).read_text(encoding='utf-8')
            for satir in metin.splitlines():
                cikarilmis = satir.split('#')[0]
                if 'BAND_TAVANI_BAR' not in cikarilmis:
                    continue
                assert f'= {tavan}' not in cikarilmis, (
                    f'{ad}: bandın tavanı sabit yazılmış ({satir.strip()!r}) '
                    '— kanonik tablodan okunmalı')


# ===========================================================================
# 2) OH-D16-09 — SARSIM ARACININ İKİ KÖR NOKTASI
# ===========================================================================

class TestOHD1609YankiSimetrisiDalAnahtarinaKorDegil:
    """(A) Bir alan koca bir alt ağacı kaldırıyorsa bu AYRIŞMA değildir.

    ``calculate_trajectory=False`` yanıttaki bütün ``.trajectory.*``
    bloğunu kaldırır. ``differing_paths`` yaprağın YOK OLMASINI da
    "değişti" sayar; kopya sözleşmesi ise değişim kümelerinin simetrik
    olmasını ister. İkisi birleşince ``.trajectory.motor_data.*`` yaprakları
    "bayat kopya şüphesi" diye işaretleniyordu — oysa hiçbiri bayat
    değildi, blok o koşuda HİÇ YOKTU.

    ÖLÇÜLDÜ (``once_shake.json`` A bölümü): bugünkü kodda sahte ayrışma
    SIFIR (``yanki_ayristi = []``, ``trajectory`` kökenli ayrışma 0) ve
    bayrak 21.245 yaprakla CANLI. Yani kalem başlığının bu yarısı bugün
    ÇÜRÜKTÜR — onarım ÖH D15/harita (``08c7878``) ile yapılmıştı. Eksik
    olan KİLİTTİ: ``ever_changed_present`` süzgeci sökülürse hiçbir bekçi
    görmüyordu. Bu sınıf o boşluğu kapatır.
    """

    @pytest.fixture(scope='class')
    def rapor(self, client):
        spec = shake.FieldSpec(name='calculate_trajectory', kind='bool')
        taban = dict(HYBRID_BASE, calculate_trajectory=True)
        return shake.run(client, '/calculate', taban, [spec])

    def test_dal_anahtari_sahte_ayrisma_uretmiyor(self, rapor):
        assert rapor.yanki_ayristi == [], (
            'dal anahtarı sarsılınca kopya sözleşmesi SAHTE ihlal verdi; '
            'kaybolan yaprak "ayrıştı" sayılıyor: '
            f'{sorted(rapor.yanki_ayristi)[:10]}')

    def test_dal_anahtari_gercekten_canli(self, rapor):
        """Sahte ayrışmanın yokluğu, alanın ölçülmemesinden gelmemeli."""
        assert 'calculate_trajectory' in rapor.live_inputs, (
            'bayrak canlı sayılmadı — sahte ayrışmanın yokluğu ölçümün '
            f'çökmesinden geliyor olabilir: {rapor.summary()}')
        assert rapor.live_inputs['calculate_trajectory'] > 100

    def test_yalniz_iki_snapshotta_da_VAR_OLAN_yaprak_simetri_ister(self):
        """Kuralın kendisi: kaybolan yaprak simetri denetimine girmez.

        Kaynak düzeyinde çivilenir ki, süzgeç sessizce sökülmesin.
        """
        import inspect
        kaynak = inspect.getsource(shake.run)
        assert 'ever_changed_present' in kaynak, (
            'simetri denetimi artık "iki snapshot\'ta da var olan" '
            'süzgecini kullanmıyor — sahte ayrışma sınıfı geri döner')
        assert 'p in context_base and p in shaken' in kaynak, (
            'süzgecin ölçütü değişmiş; kaybolan yaprak yine "ayrıştı" '
            'sayılabilir')


class TestOHD1609IkiliAlanTahminEdilmez:
    """(B) Taban değeri bilinmeyen ikili alan SARSILAMAZ, uydurulamaz.

    ``perturb`` eskiden ``not bool(current)`` yazıyordu; alan taban yükte
    yoksa ``current=None`` -> ``True`` üretiliyordu ve bu, çoğu bayrakta
    ucun zaten kullandığı varsayılandır. Sarsım hiçbir şeyi değiştirmiyor,
    çıktı bit-aynı çıkıyor, CANLI alan ÖLÜ ilan ediliyordu.

    ÖLÇÜLDÜ (``once_shake.json`` ⟷ ``sonra_shake.json``, ``bayraksiz_taban``):
    ``calculate_trajectory`` taban yükten çıkarıldığında ÖNCE
    ``dead_inputs=['calculate_trajectory']``, SONRA ``unmeasurable`` içinde
    adıyla + gerekçesiyle. Hibrit yolunda bunu
    ``test_field_wiring_layer_b.py`` taban yükü zorunlu kılarak koruyordu;
    katı/sıvı yolunda (``tools/wiring_map.py::measure_page`` yalnız
    ``choice`` alanlarını geri doldurur) kilit YOKTU.
    """

    def test_taban_degeri_bilinmeyen_bayrak_sarsilamaz(self):
        spec = shake.FieldSpec(name='calculate_trajectory', kind='bool')
        assert shake.perturb(spec, None) is None, (
            'taban değeri bilinmeyen ikili alan için sarsım değeri '
            'UYDURULDU; ucun varsayılanına çarpacağı için alan sahte ÖLÜ '
            'görünür')

    @pytest.mark.parametrize('mevcut,beklenen', [(True, False), (False, True),
                                                 (0, True), (1, False)])
    def test_taban_degeri_bilinen_bayrak_hala_cevriliyor(self, mevcut,
                                                         beklenen):
        """Fail-closed olmak, ölçümü kısırlaştırmak değildir."""
        spec = shake.FieldSpec(name='her_neyse', kind='bool')
        assert shake.perturb(spec, mevcut) is beklenen

    def test_bildirilmemis_bayrak_OLU_degil_OLCULEMEDI(self, client):
        """Sınıfın asıl iddiası: sessiz yanlış hüküm yerine adlı ret."""
        spec = shake.FieldSpec(name='calculate_trajectory', kind='bool')
        taban = {k: v for k, v in HYBRID_BASE.items()
                 if k != 'calculate_trajectory'}
        rapor = shake.run(client, '/calculate', taban, [spec])
        assert 'calculate_trajectory' not in rapor.dead_inputs, (
            'bildirilmemiş bayrak hâlâ ÖLÜ ilan ediliyor — sahte hüküm')
        gerekce = rapor.unmeasurable.get('calculate_trajectory')
        assert gerekce, (
            'bildirilmemiş bayrak ne ölü ne ölçülemedi diye görünüyor; '
            f'ölçüm sessizce kayboldu: {rapor.summary()}')
        assert 'taban' in gerekce, (
            f'ölçülemedi gerekçesi NEDENİNİ söylemiyor: {gerekce!r}')


# ===========================================================================
# 3) P10B4-06 — SEÇİM ALANI 1/N SARSILIYOR; KAPSAM BEYAN EDİLİR
# ===========================================================================
#
# ÖLÇÜLEN NÜFUS — TEK KAYNAK (ÖH D33 fix-36, taban kaydı-16 sınıflandırması)
# -------------------------------------------------------------------------
# Bu iki sayı ŞABLONDAN ölçülür ve aşağıdaki İKİ sınıf tarafından paylaşılır;
# daha önce ayrı ayrı çivilendikleri için şablon değişince biri güncellenip
# diğeri bayat kalabiliyordu (ölçüldü: D32'de d15 sayım mandalı çevrildi,
# buradaki harita bekçisi atlandı → taban kaydı-16'da 3 kırmızı).
#
# ÖNCE (P10 B4, ``once_shake.json`` C bölümü):  evren 11, kırık 4
#     {'carbon', 'al2o3', 'mixture', 'custom'} — hepsi HTTP 400
# SONRA (ÖH D32 arayuz-panel a1, 577bb32d · OH-D31-05; hüküm-21 KABUL):
#     ``al2o3`` seçeneği ŞABLONDAN KALDIRILDI — kategori hatası (alüminyum
#     oksit yakıt değildir; uç zaten ``not_a_fuel`` ile reddediyordu).
#     Evren 11 → 10, kırık küme 4 → 3.
#
# Kırık küme KÜÇÜLDÜ ama bu bir GEVŞEME DEĞİLDİR: kalkan seçenek uçta
# onarılmadı, kullanıcıya SUNULMAYI bıraktı. Gevşemeyi engellemek için
# aşağıdaki ``SOKULEN_SECENEKLER`` çapası var: sökülen ad evrene sessizce
# geri dönerse bekçi kırmızı olur (geri dönüş ancak uç onarımı + defter
# kaydı + bu blok BİRLİKTE güncellenerek meşrulaşır).
#: Şablonun yayımladığı ``fuel_type`` seçenek sayısı (ölçüldü: 10).
FUEL_TYPE_SECENEK = 10

#: Uçtan HTTP >=400 dönen, yani listede görünüp çözülmeyen seçenekler.
KIRIK_SECENEKLER = frozenset({'carbon', 'mixture', 'custom'})

#: OH-D31-05 ile şablondan SÖKÜLEN seçenekler. Uçta onarılmadılar; geri
#: gelirlerse yeniden kırık seçenek olurlar — sessiz dönüş yasak.
SOKULEN_SECENEKLER = frozenset({'al2o3'})

class TestP10B406SecimKapsamiBeyanEdilir:
    """"Canlı" hükmü kaç seçenekten kaçına dayanıyor?

    ÖLÇÜLDÜ (P10 B4 + ``once_shake.json`` C bölümü): hibritte ``fuel_type``
    11 seçenek taşıyor; ``carbon``, ``al2o3``, ``mixture`` ve ``custom``
    uçtan HTTP 400 dönüyor (``Unsupported fuel key ...``). Buna rağmen
    sarsım raporu ``unmeasurable = {}``, ``dead = []`` ve
    ``live = {'fuel_type': 28980}`` diyordu: alan tam canlı görünüyordu,
    kullanıcının açılır listede görebildiği dört kırık seçenek hiçbir
    yerde yoktu. Haritanın dürüstlük sözü ("ölçülemeyen alan ölü diye
    işaretlenmez") ÜÇÜNCÜ hâli tanımıyordu — kısmen ölçüldü.

    ÖH D32 GÜNCELLEMESİ (577bb32d · OH-D31-05): ``al2o3`` şablondan
    sökülünce evren 11 → 10, kırık küme 4 → 3 oldu. Yukarıdaki P10 ölçümü
    TARİHÎ kayıttır ve olduğu gibi durur; bugünkü nüfus modül başındaki
    ``FUEL_TYPE_SECENEK`` / ``KIRIK_SECENEKLER`` sabitlerindedir.
    """

    @pytest.fixture(scope='class')
    def yakit_secenekleri(self):
        alan = inventory.field_specs_for('hybrid').get('fuel_type')
        assert alan is not None, 'fuel_type şablon envanterinde yok'
        secenekler = tuple(alan.options or ())
        assert len(secenekler) >= 8, (
            f'seçenek evreni beklenmedik ölçüde küçük: {secenekler}')
        assert len(secenekler) == FUEL_TYPE_SECENEK, (
            f'fuel_type seçenek evreni {len(secenekler)}; ölçülen nüfus '
            f'{FUEL_TYPE_SECENEK}. Şablon değiştiyse modül başındaki '
            'FUEL_TYPE_SECENEK / KIRIK_SECENEKLER sabitleri ve defter '
            f'kaydı BİRLİKTE güncellensin: {secenekler}')
        geri_donen = sorted(SOKULEN_SECENEKLER.intersection(secenekler))
        assert not geri_donen, (
            f'OH-D31-05 ile sökülen seçenek listeye geri gelmiş: '
            f'{geri_donen}. Uç bu yakıtı gerçekten çözüyorsa onarım defter '
            'kaydıyla birlikte yazılır; çözmüyorsa kullanıcıya yine kırık '
            'seçenek sunuluyor demektir')
        return secenekler

    def test_kapsam_hukumle_birlikte_yayimlanir(self, client,
                                                yakit_secenekleri):
        """Sarsım 1/N ise rapor bunu ADIYLA söylemeli."""
        spec = shake.FieldSpec(name='fuel_type', kind='choice',
                               options=yakit_secenekleri)
        rapor = shake.run(client, '/calculate', dict(HYBRID_BASE), [spec])
        kapsam = rapor.secim_kapsami.get('fuel_type')
        assert kapsam, (
            'seçim alanı sarsıldı ama kapsam beyanı yok — "canlı" hükmü '
            'kaç seçeneğe dayandığını saklıyor')
        assert kapsam['toplam'] == len(yakit_secenekleri)
        assert kapsam['denenen'] == 1, (
            'varsayılan sarsım hâlâ tek alternatif denemeli (pahalı süpürme '
            f'opt-in olmalı): {kapsam}')
        assert kapsam['denenen'] < kapsam['toplam'], (
            'kapsam beyanı anlamsız: denenen == toplam ama süpürme kapalı')

    def test_supurme_kirik_secenekleri_ADIYLA_bildirir(self, client,
                                                       yakit_secenekleri):
        spec = shake.FieldSpec(name='fuel_type', kind='choice',
                               options=yakit_secenekleri)
        rapor = shake.run(client, '/calculate', dict(HYBRID_BASE), [spec],
                          probe_all_options=True)
        kismen = rapor.kismen_olculdu.get('fuel_type')
        assert kismen, (
            'bütün seçenekler denendiği hâlde kırık seçenek bildirilmedi — '
            'ya uç onarıldı (o zaman bu bekçi güncellenmeli) ya da üçüncü '
            f'hâl yine görünmüyor: {rapor.summary()}')
        kirik = kismen['kirik']
        assert set(kirik) >= set(KIRIK_SECENEKLER), (
            'ölçülen kırık seçeneklerden bazıları bildirilmiyor '
            f'(beklenen {sorted(KIRIK_SECENEKLER)}): {sorted(kirik)}')
        assert all(int(durum) >= 400 for durum in kirik.values()), (
            f'kırık seçenek listesi 200 dönen seçenek taşıyor: {kirik}')
        assert kismen['denenen'] == len(yakit_secenekleri) - 1

    def test_calisan_secenekler_kirik_listesine_girmez(self, client,
                                                       yakit_secenekleri):
        """Üçüncü hâl bir çöp kutusu değil: yalnız gerçek kırıklar."""
        spec = shake.FieldSpec(name='fuel_type', kind='choice',
                               options=yakit_secenekleri)
        rapor = shake.run(client, '/calculate', dict(HYBRID_BASE), [spec],
                          probe_all_options=True)
        kirik = set(rapor.kismen_olculdu['fuel_type']['kirik'])
        for calisan in ('htpb', 'pe', 'paraffin', 'abs'):
            assert calisan not in kirik, (
                f'{calisan} çalıştığı hâlde kırık sayıldı: {sorted(kirik)}')

    def test_kismen_olculen_alan_ozette_gorunur(self, client,
                                               yakit_secenekleri):
        """Beyan, özet satırında da yaşamalı — rapora bakan görsün."""
        spec = shake.FieldSpec(name='fuel_type', kind='choice',
                               options=yakit_secenekleri)
        rapor = shake.run(client, '/calculate', dict(HYBRID_BASE), [spec],
                          probe_all_options=True)
        assert 'kismen olculdu' in rapor.summary(), rapor.summary()
        assert '1 kismen olculdu' in rapor.summary(), rapor.summary()


# ===========================================================================
# 3b) P10B4-06 (Fable-D17 ŞART'ı) — KAPSAM BEYANI HARİTADA DA YAYIMLANIR
# ===========================================================================

class TestP10B406HaritaKapsamiYayimlar:
    """Kapsam beyanı bellek içinde kaldı mı, kullanıcının haritasına çıktı mı?

    Fable-D17 ŞART'ı: D17 onarımı ``ShakeReport.secim_kapsami`` /
    ``kismen_olculdu`` alanlarını DOĞRU kurmuştu, ama haritayı üreten
    ``tools/wiring_map.py`` ``data`` sözlüğü bu iki alanı ANMIYORDU
    (ölçüldü: ``git grep secim_kapsami tools/`` → 0 satır). Kullanıcının
    gördüğü harita 1/N sarsımını kapsam beyanı olmadan "canlı" gösteriyordu
    — kusurun kullanıcıya bakan yüzü kapanmamıştı.

    ÖLÇÜM (ÖH D20, ``once_supurme_maliyeti.json`` / ``sonra_harita.json``):

    * ``/calculate`` çağrısı 0,93 sn; hibrit ``fuel_type`` süpürmesi 10 ek
      çağrı = 9,3 sn; ÜÇ sayfanın TAM süpürmesi 124 ek çağrı ≈ 116 sn.
      Karar bu ölçümle verildi: tam süpürme ``--supurme`` bayrağına bağlı,
      kırık seçeneği ÖLÇÜLMÜŞ alanlar (``SUPURULEN_ALANLAR``) her koşuda
      süpürülür.
    * Canlı harita koşumu (``--page hybrid``): ``secimKapsami.fuel_type``
      = {toplam 11, denenen 10}, ``kismenOlculdu.fuel_type.kirik`` =
      {carbon, al2o3, mixture, custom: 400}.

    ÖH D32 GÜNCELLEMESİ (577bb32d · OH-D31-05): ``al2o3`` şablondan
    söküldü; bugünkü koşum {toplam 10, denenen 9} ve kırık küme
    {carbon, mixture, custom: 400} ölçüyor. Yukarıdaki D20 satırı TARİHÎ
    ölçümdür, olduğu gibi durur; yürürlükteki nüfus modül başındaki
    ``FUEL_TYPE_SECENEK`` / ``KIRIK_SECENEKLER`` sabitleridir.
    """

    # Şablonun yayımladığı seçenek sayısı modül başındaki TEK KAYNAKTAN
    # (``FUEL_TYPE_SECENEK``) okunur. Bu sınıf sayıyı ayrıca çivilemez:
    # D32'de iki ayrı çivi yüzünden biri güncellenip diğeri bayat kalmıştı
    # (taban kaydı-16, 3 kırmızı). Sayı DEĞİŞİRSE harita hükmü de değişir;
    # sessizce olmamalı (ŞART: "fuel_type için toplam çivilensin").

    @pytest.fixture(scope='class')
    def harita_verisi(self, client):
        """Gerçek sarsımdan gerçek harita HTML'i üretir ve JSON'unu okur.

        Kayıt kilidi DEĞİL ağaç kilidi: ``build_html`` çağrılır ve sayfaya
        gömülen ``const D = {...}`` çözümlenir.
        """
        import re as _re
        import sys as _sys
        import pathlib as _pathlib
        kok = _pathlib.Path(__file__).resolve().parent.parent
        _sys.path.insert(0, str(kok / 'tools'))
        import wiring_map                                   # noqa: E402

        alan = inventory.field_specs_for('hybrid')['fuel_type']
        spec = shake.FieldSpec(name='fuel_type', kind='choice',
                               options=tuple(alan.options or ()))
        rapor = shake.run(client, '/calculate', dict(HYBRID_BASE), [spec],
                          probe_fields=wiring_map.SUPURULEN_ALANLAR['hybrid'])
        html = wiring_map.build_html('hybrid', rapor, None,
                                     {'fuel_type': 'fuel_type'}, '—')
        m = _re.search(r'const D = (\{.*?\});\n', html, _re.S)
        assert m, 'harita sayfasında gömülü JSON bulunamadı'
        return json.loads(m.group(1)), html

    def test_harita_JSONunda_secim_kapsami_var(self, harita_verisi):
        """ŞART'ın birinci yarısı: anahtarın VARLIĞI."""
        data, _html = harita_verisi
        assert 'secimKapsami' in data, (
            'harita "canlı" diyor ama hükmün kaç seçeneğe dayandığını '
            'yayımlamıyor — kapsam beyanı yine bellekte kaldı')
        assert 'kismenOlculdu' in data

    def test_fuel_type_toplami_olculen_nufus(self, harita_verisi):
        """ŞART'ın ikinci yarısı: fuel_type toplamı çivili.

        ÖH D33 fix-36 — DÜĞÜM ADI SAYIDAN ARINDIRILDI. Ad ``..._onbir``
        idi; OH-D31-05 evreni 10'a indirince ad YALAN SÖYLEMEYE başladı
        (yeşil bir bekçi "onbir" diyordu). Sayı artık yalnız modül
        başındaki ``FUEL_TYPE_SECENEK`` sabitinde durur — tek yerde.
        """
        data, _html = harita_verisi
        kapsam = data['secimKapsami'].get('fuel_type')
        assert kapsam, 'fuel_type kapsamı haritada yok'
        assert kapsam['toplam'] == FUEL_TYPE_SECENEK, (
            f"fuel_type seçenek evreni {kapsam['toplam']}; ölçülen taban "
            f'{FUEL_TYPE_SECENEK}. Şablon değiştiyse harita hükmü ve '
            'defter kaydı birlikte güncellensin')
        # Süpürme kırık seçeneği BİLİNEN alanda her koşuda açık.
        assert kapsam['denenen'] == FUEL_TYPE_SECENEK - 1

    def test_kirik_secenekler_haritada_ADIYLA_duruyor(self, harita_verisi):
        """Kullanıcının listede gördüğü kırık seçenek görünmez kalmaz."""
        data, _html = harita_verisi
        kirik = (data['kismenOlculdu'].get('fuel_type') or {}).get('kirik')
        assert kirik, (
            'süpürme açık ama düşen seçenek yayımlanmadı — alan yine tam '
            'canlı görünüyor')
        assert set(kirik) >= set(KIRIK_SECENEKLER), (
            f'harita kırık kümesi eksik (beklenen '
            f'{sorted(KIRIK_SECENEKLER)}): {kirik}')
        assert all(int(d) >= 400 for d in kirik.values())

    def test_kullanici_yuzu_kapsami_gosteriyor(self, harita_verisi):
        """Sayı JSON'da durup ekranda görünmüyorsa kusur kapanmamıştır."""
        _data, html = harita_verisi
        assert 'kapsamRozeti' in html, (
            'harita arayüzü kapsam rozetini çizmiyor')
        assert 'denendi' in html
        assert 'seçim alanı' in html, (
            'sayfa başlığındaki meta satırı seçim kapsamını anmıyor')


# ===========================================================================
# 4) OH-Z5-15 / OH-D16-15 — TABLO KAYDI (çapraz kilit)
# ===========================================================================

class TestOHZ515TabloBosalmadi:
    """``test_z5s_ham_500`` tablosunun ÖLÇÜLMÜŞ hâli burada da çivilenir.

    Aynı kusurun iki kimliği var (Fable-D15 ŞART'ı OH-Z5-15 ve D16 bulgusu
    OH-D16-15): 13 vakanın 8'i kalıcı ``skip`` olduğu için bekçi fiilen
    boşalmıştı. Onarım o dosyada yapıldı; buradaki kilit, tablonun ileride
    sessizce yeniden zayıflamasını (skip'e dönmesini ya da zor hükümlerin
    kolayına çevrilmesini) engeller.
    """

    def test_tabloda_skip_kalmadi(self):
        from tests.test_z5s_ham_500 import (YOKLUK_NULL_CIFTLERI,
                                            YOKLUK_NULL_HUKUM_DAGILIMI)
        assert len(YOKLUK_NULL_CIFTLERI) == 13
        hukumler = {h for _y, _a, _t, h in YOKLUK_NULL_CIFTLERI}
        assert hukumler <= {'beyan', 'kunye', 'fail_closed'}, hukumler
        # ÖH D33-2 / app-api-uc a1 (OH-D32-13) — MANDAL ÇEVRİLDİ, İDDİA
        # SERTLEŞTİ. Eski satır dağılımı SABİT bir sözlüğe (10/1/2)
        # bağlıyordu; bu, bir vakanın ZORA geçmesini de yasaklıyordu.
        # Akış ucunun dört zorunlu alanı ``beyan``dan ``fail_closed``a
        # geçince (kapı alan-alan indi) bekçi kusurun ONARILMASINI
        # engelleyen bir mandala dönüşecekti. Kilit artık YÖNLÜ: toplam
        # sabit, ``fail_closed`` AZALAMAZ, ``beyan`` ARTAMAZ — yani
        # tabloyu kolaya çekmek hâlâ yasak, zora çekmek serbest.
        assert sum(YOKLUK_NULL_HUKUM_DAGILIMI.values()) == 13
        assert set(YOKLUK_NULL_HUKUM_DAGILIMI) == {'beyan', 'kunye',
                                                   'fail_closed'}
        assert YOKLUK_NULL_HUKUM_DAGILIMI['fail_closed'] >= 2, (
            'fail_closed vaka sayısı DÜŞMÜŞ — hüküm zayıflatılmış')
        assert YOKLUK_NULL_HUKUM_DAGILIMI['beyan'] <= 10, (
            'beyan vakası ARTMIŞ — kapı künyeye çevrilmiş olabilir')
        assert YOKLUK_NULL_HUKUM_DAGILIMI['kunye'] == 1
        # Sözlük tablonun KENDİSİNDEN kopmamalı (tek kaynak).
        gercek = {}
        for _y, _a, _t, _h in YOKLUK_NULL_CIFTLERI:
            gercek[_h] = gercek.get(_h, 0) + 1
        assert gercek == YOKLUK_NULL_HUKUM_DAGILIMI, (gercek,
                                                      YOKLUK_NULL_HUKUM_DAGILIMI)

    def test_bekci_skip_etmiyor(self):
        """Kaynak düzeyinde: ``pytest.skip`` bu bekçiye geri konamaz.

        Yalnız YÜRÜTÜLEN gövdeye bakılır; docstring kusurun tarihçesini
        anlatmakta serbesttir (aksi hâlde bekçi kendi gerekçesini yasaklar).
        """
        import ast
        import inspect
        from tests.test_z5s_ham_500 import TestYoklukIleAcikNullAyni
        kaynak = inspect.getsource(
            TestYoklukIleAcikNullAyni.test_dusus_sessiz_degil)
        agac = ast.parse(inspect.cleandoc(kaynak))
        cagrilar = {
            ast.unparse(dugum.func)
            for dugum in ast.walk(agac)
            if isinstance(dugum, ast.Call) and hasattr(dugum, 'func')
        }
        atlayanlar = {ad for ad in cagrilar if 'skip' in ad}
        assert not atlayanlar, (
            '"düşüş sessiz değil" bekçisine yeniden atlama konmuş '
            f'({sorted(atlayanlar)}) — atlama bir hüküm değildir')

    def test_kanit_dosyasi_tabloyla_tutarli(self):
        """Rapor sayıları ölçüm dosyasından gelir, elle yazılmaz."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent.parent
        kanit = (kok / 'docs/scofield/raw/OH/D17/bekci-cevirisi/a1'
                 / 'once_ohz515b.json')
        if not kanit_gerekli(kanit).is_file():                       # pragma: no cover
            pytest.skip('kanıt dosyası bu ağaçta yok')
        veri = json.loads(kanit_gerekli(kanit).read_text(encoding='utf-8'))
        ozet = veri['ozet']
        assert ozet['toplam'] == 13 and ozet['skip'] == 0
        assert ozet['beyan'] == 10 and ozet['fail_closed'] == 2
        assert ozet['kunye'] == 1
        assert ozet['ayni_hukum_ihlali'] == []


# ===========================================================================
# 5) OH-Z4-02 — Z4 BEKÇİ BORÇLARININ ENVANTERİ + AÇIK KALAN BORÇ
# ===========================================================================

#: Yedi borcun ADRESİ. Değer boşsa borç henüz ödenmemiştir.
#: ÖLÇÜLDÜ (``once_ohz402.json``): D16 raporu 2/7 kilitli diyordu; koda
#: bakınca (1), (3), (5) ve (6) Z5S bekçi-ödeme paketleriyle 27 Ağu'da
#: ZATEN kilitlenmişti — kalem notu bayattı. Gerçekten açık olan tek borç
#: (4) idi ve bu dosyada ödendi.
OH_Z402_BORCLARI = {
    '1_manset_degismeli': [
        ('tests/test_z5guard_panel_motor.py',
         'test_a1_manset_cidar_supurmesinde_degisiyor'),
        ('tests/test_z5guard_panel_motor.py',
         'test_a3_calculate_ucu_da_cidara_duyarli'),
    ],
    '2_wall_thickness_source_uc_rozet': [
        ('tests/test_d16_bekci_cevirisi_a1.py',
         'TestOHZ402CidarRozetiUcSinif'),
    ],
    '3_cift_sf_etiketi': [
        ('tests/test_z5guard_urun_tur.py', 'TestP17B3_06CiftSFEtiketi'),
        ('tests/test_z5guard_panel_motor.py',
         'test_a2_hedef_geri_okumasi_ayri_satirda_ve_donuk'),
    ],
    '4_yalitimli_vaka_akma_duyarliligi': [
        ('tests/test_d17_bekci_cevirisi_a1.py',
         'TestOHZ402YalitimAkmaDuyarliligi'),
    ],
    '5_converged_kapisi': [
        ('tests/test_z5guard_urun_tur.py', 'TestP17B1_02YakinsamaKapisi'),
    ],
    '6_kiyas_beyani_bridge': [
        ('tests/test_z5guard_urun_tur.py', 'TestP8B2_11KopruKiyasBeyani'),
    ],
    '7_kunye_tanimi': [
        ('tests/test_d16_bekci_cevirisi_a1.py', 'TestOHZ402KunyeTanimi'),
    ],
}


def _bekci_canliligi(dosya, ad):
    """Adreslenen bekçi CANLI mı? ('CANLI' | 'OLU' | 'YOK', gerekçe)

    ÖH D29 / OH-D19-26 (c) — ADRES KİLİDİ METİN ARAMASIYDI. Eski hâl
    ``f'def {ad}' in metin`` diyordu; bu kilit borç ödeyen bekçinin
    ``@pytest.mark.xfail`` ile susturulmuş, ``@pytest.mark.skip`` ile
    atlanmış ya da gövdesi yalnız ``pass``/docstring bırakılmış hâlini
    GÖREMEZ — yani "borç ödendi" beyanı, hiçbir şey sınamayan bir isimle
    yeşil kalabilirdi. ÖLÇÜLDÜ (raw/OH/D29/arayuz-i18n/a1/
    {once,sonra}_kalan.json, K1): kilit metin aramasıydı (1), canlılık
    denetimi yoktu (0); bugün 9 adresin 9'u canlı, yani bu bir REGRESYON
    kapısıdır — kusur gelecekte sessizce açılırdı.

    Sınıf adresinde en az bir canlı ``test_*`` üyesi aranır: bütün
    üyeleri xfail'e çevrilmiş bir sınıf da ölüdür.
    """
    import ast
    import pathlib
    yol = pathlib.Path(__file__).resolve().parent.parent / dosya
    if not yol.is_file():
        return 'YOK', 'dosya yok'
    try:
        agac = ast.parse(yol.read_text(encoding='utf-8'))
    except SyntaxError as exc:  # pragma: no cover
        return 'OLU', f'ayrıştırılamıyor: {exc}'

    def _imler(dugum):
        return ' '.join(ast.unparse(d) for d in dugum.decorator_list)

    def _bos_govde(dugum):
        return all(isinstance(s, ast.Pass)
                   or (isinstance(s, ast.Expr)
                       and isinstance(s.value, ast.Constant))
                   for s in dugum.body)

    def _fn_canli(dugum):
        im = _imler(dugum)
        if 'xfail' in im or 'skip' in im:
            return False, 'xfail/skip imli'
        if _bos_govde(dugum):
            return False, 'gövdesi boş (pass/docstring)'
        return True, ''

    for dugum in ast.walk(agac):
        if getattr(dugum, 'name', None) != ad:
            continue
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
            canli, gerekce = _fn_canli(dugum)
            return ('CANLI', '') if canli else ('OLU', gerekce)
        if isinstance(dugum, ast.ClassDef):
            im = _imler(dugum)
            if 'xfail' in im or 'skip' in im:
                return 'OLU', 'sınıf xfail/skip imli'
            uyeler = [u for u in dugum.body
                      if isinstance(u, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and u.name.startswith('test_')]
            if not uyeler:
                return 'OLU', 'sınıfta test_* üyesi yok'
            if not any(_fn_canli(u)[0] for u in uyeler):
                return 'OLU', 'sınıfın bütün test_* üyeleri ölü'
            return 'CANLI', ''
    return 'YOK', 'ad dosyada tanımlı değil'


class TestOHZ402BorcEnvanteri:
    """Borç listesi bir metin değil, ADRES listesidir.

    Kusurun biçimi: "toplu bekçi paketi" kalemleri yıllarca açık kalır
    çünkü hangi borcun hangi bekçiyle ödendiği hiçbir yerde MAKİNEYLE
    yazılı değildir; rapor notu bayatlar (bu kalemde tam bu oldu — D16
    notu 5 borç açık diyordu, koda bakınca 4'ü ödenmişti). Aşağıdaki
    tablo o eşlemeyi koda taşır: adres kaybolursa test kırmızı verir.
    """

    @pytest.mark.parametrize('borc', sorted(OH_Z402_BORCLARI))
    def test_borcun_bekcisi_dosyada_duruyor(self, borc):
        adresler = OH_Z402_BORCLARI[borc]
        assert adresler, f'{borc}: borç ADRESSİZ — bekçisi yok'
        bulunan, olu = [], []
        for dosya, ad in adresler:
            durum, gerekce = _bekci_canliligi(dosya, ad)
            if durum == 'CANLI':
                bulunan.append(f'{dosya}::{ad}')
            elif durum == 'OLU':
                olu.append(f'{dosya}::{ad} ({gerekce})')
        assert not olu, (
            f'{borc}: adreslenen bekçi VAR ama ÖLÜ — borç ödenmiş '
            f'görünüyor, ödenmemiş: {olu}')
        assert bulunan, (
            f'{borc}: bildirilen bekçilerin hiçbiri dosyada yok '
            f'({adresler}) — borç sessizce ödenmemiş sayılır')

    def test_yedi_borcun_yedisi_de_adreslendi(self):
        assert len(OH_Z402_BORCLARI) == 7
        adressiz = [b for b, a in OH_Z402_BORCLARI.items() if not a]
        assert not adressiz, adressiz


class TestOHZ402YalitimAkmaDuyarliligi:
    """(4) OH-Z2-08 kapanış şartı: akma basıncı YALITIMA duyarlı olmalı.

    Kusur (OH-Z2-08, kapatıldı 2422558): hoop yarıçapı olarak grain
    yarıçapı (``D_chamber/2``) kullanılıyordu. Basınç ise yalıtımdan geçip
    METAL kabuğun iç yüzüne biner; taşıyıcı yarıçap kasa iç yarıçapıdır
    (grain + 2·yalıtım). Eski formül akma basıncını ``1 + 2·t_ins/D``
    çarpanıyla TEHLİKELİ yönde şişiriyordu — 5 mm yalıtımda +%10.

    Ürün onarıldı ama kapanış şartının bekçi yarısı (OH-Z4-02 §4)
    ödenmemişti: bugün ``r_inner`` satırı ``D_chamber/2``ye geri
    çevrilse hiçbir test kırmızı vermiyordu.

    ÖLÇÜLDÜ (``once_ohz402.json``): cidar SABİT 6 mm, yalıtım
    0 / 2 / 5 / 10 mm süpürmesinde ``pressure_safety.yield_pressure_bar``
    monoton DÜŞÜYOR ve düşüş oranı geometrik beklentiyle
    (``D_kasa(0)/D_kasa(t)``) 1e-9 içinde örtüşüyor.
    """

    CIDAR_MM = 6.0
    YALITIM_MM = (0.0, 2.0, 5.0, 10.0)

    @staticmethod
    def _kap(t_ins_mm, cidar_mm):
        import warnings as _uyari
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        with _uyari.catch_warnings():
            _uyari.simplefilter('ignore')
            motor = SolidRocketEngine(
                grain_type='bates', propellant_type='apcp',
                chamber_diameter=100.0, grain_length=500.0,
                core_diameter=30.0, chamber_pressure=40,
                overrides={'case_thickness': cidar_mm,
                           'insulation_thickness': t_ins_mm})
            govde = motor._calculate_safety_analysis(
                motor.calculate_thrust_curve())
        return motor, govde['pressure_safety']

    @pytest.fixture(scope='class')
    def supurme(self):
        return {t: self._kap(t, self.CIDAR_MM) for t in self.YALITIM_MM}

    def test_yalitim_kasa_ic_capina_giriyor(self, supurme):
        """Ön koşul: fikstür gerçekten yalıtımı değiştiriyor."""
        caplar = {t: motor._case_inner_diameter()
                  for t, (motor, _ps) in supurme.items()}
        assert len(set(round(c, 9) for c in caplar.values())) == \
            len(self.YALITIM_MM), caplar
        for t in self.YALITIM_MM:
            assert caplar[t] == pytest.approx(caplar[0.0] + 2 * t / 1000.0,
                                              abs=1e-9), (t, caplar)

    def test_cidar_supurme_boyunca_SABIT(self, supurme):
        """Duyarlılık yalıtımdan gelmeli, cidarın kaymasından değil."""
        for t, (_motor, ps) in supurme.items():
            assert ps['case_wall_thickness_mm'] == pytest.approx(
                self.CIDAR_MM, abs=1e-9), (t, ps['case_wall_thickness_mm'])

    def test_akma_basinci_yalitimla_DUSUYOR(self, supurme):
        akmalar = [supurme[t][1]['yield_pressure_bar']
                   for t in self.YALITIM_MM]
        for onceki, sonraki in zip(akmalar, akmalar[1:]):
            assert sonraki < onceki, (
                'akma basıncı yalıtım kalınlaşınca düşmedi — hoop yarıçapı '
                f'yine grain yarıçapı olabilir (OH-Z2-08): {akmalar}')

    def test_dusus_geometrik_beklentiyle_ORTUSUYOR(self, supurme):
        """Sayı uydurulmadı: oran kasa iç çaplarının oranı olmalı."""
        motor0, ps0 = supurme[0.0]
        d0 = motor0._case_inner_diameter()
        for t in self.YALITIM_MM[1:]:
            motor_t, ps_t = supurme[t]
            beklenen = ps0['yield_pressure_bar'] * d0 / \
                motor_t._case_inner_diameter()
            assert ps_t['yield_pressure_bar'] == pytest.approx(
                beklenen, rel=1e-9), (
                f'{t} mm yalıtımda akma basıncı {ps_t["yield_pressure_bar"]!r}, '
                f'geometrik beklenti {beklenen!r} — sigma_y*t/r bağıntısı '
                'kasa iç yarıçapını kullanmıyor')

    def test_basinc_emniyet_katsayisi_da_duyarli(self, supurme):
        """Hüküm de kaymalı: SF akma basıncından türüyor."""
        sfler = [supurme[t][1]['safety_factor'] for t in self.YALITIM_MM]
        assert sfler[0] > sfler[-1], (
            f'yalıtım 10 mm iken emniyet katsayısı düşmedi: {sfler}')

    def test_on_dokuzuncu_basamak_capalanmadi(self, supurme):
        """Bekçi ondalık çapası DEĞİL: mutlak sayı sabitlenmiyor."""
        import inspect
        kaynak = inspect.getsource(type(self))
        assert 'yield_pressure_bar' in kaynak
        # Sınıfın kendi kaynağında yayımlanan bir bar değeri yazılı olmamalı.
        for _t, (_motor, ps) in supurme.items():
            assert repr(round(ps['yield_pressure_bar'], 3)) not in kaynak


# ===========================================================================
# 6) D15-BEKCI-04 + OH-D16-18 — XPASS(strict) İM ENVANTERİ
# ===========================================================================

class TestD15Bekci04XpassEnvanteri:
    """İm SÖKÜLMEZ; envanter EKSİK KALAMAZ.

    Proje kuralı: ``xfail(strict=True)`` bir kapanış ölçütüdür. Ürün
    onarılınca test XPASS verir ve süit KIRMIZI olur — bu, borcun
    "ödendi ama kimse fark etmedi" hâline düşmesini engeller.

    D15-BEKCI-04 bu envanteri çıkarmıştı ama YALNIZ tek dosya için
    (``test_analysis_dock_contract.py``); OH-D16-18 tam bu eksikliği
    kaydediyor. ÖH D17'de envanter DEPO GENELİNE çıkarıldı
    (``olcum_xpass.py`` -> ``once_xpass.json``): 34 ``strict`` im,
    22 dosya, 2'si defter kimliği taşımıyor. (ÖH D25 fix-23 ölçümü: 33 im /
    22 dosya / 5'i kimliksiz — bir borç kapandığı için im söküldü, aşağıdaki
    taban notuna bakın.)

    BUGÜNKÜ TABAN (ÖH D27 fix-26a, 8 Eylül 2026): **17 im / 13 dosya**.
    D26'nın kulvarları birleşince 17 borç birden kapandı ve imleri söküldü;
    hepsi ölçüm dosyasında dosya-ad-kimlik-commit dörtlüsüyle kayıtlı.
    Taban artık bu sınıfta TAM SAYI olarak yazılı değil, ölçüm dosyasından
    türetilir ve ağaçla KÜME olarak karşılaştırılır.

    ÇALIŞTIRILDI (ÖH D17, iki toplu koşum, 22 dosya): 47 xfailed,
    **0 xpassed**. Bu sınıf envanterin bir daha tek dosyaya çökmemesini —
    ve artık hangi imin gittiğinin/geldiğinin ADIYLA görünmesini kilitler.
    """

    #: Ölçülen taban (once_xpass.json). Sayı DÜŞERSE bu bir kapanıştır ve
    #: bilinçli olmalıdır; ARTARSA yeni borç imi konmuştur, o da bilinçli
    #: olmalıdır. İkisi de sessizce olmamalı.
    #:
    #: ÖH D20 (Fable-D17 ŞART'ı): bu iddia artık TAM EŞİTLİKTİR. Eski band
    #: (``>= taban-4`` / ``>= taban-2``) dört ime kadar sökümü ve SINIRSIZ
    #: artışı sessizce geçiriyordu; yani sınıf kendi docstring'indeki
    #: "sessizce olmamalı" sözünü taşımıyordu (Doktrin: sayı üretmeyen
    #: kabul). Taban 14acd1d'de yeniden ölçüldü ve DEĞİŞMEDİ: 34 im / 22
    #: dosya (``docs/scofield/raw/OH/D20/bekci-cevirisi/a1/once.json``
    #: bölüm B). Sayı değişirse bu sabitler ve ``once_xpass.json``
    #: BİRLİKTE güncellenir — kırmızı, güncellemenin kendisidir.
    #:
    #: ÖH D25 fix-23 (5 Eylül 2026): 34 -> 33. Bekçi TAM OLARAK istediği işi
    #: yaptı: D24 birleşince sayı düştü, kırmızı verdi, kapanış BİLİNÇLİ
    #: olarak buraya yazılıyor. SÖKÜLEN İM ÖLÇÜLDÜ (AST envanteri 88a29d3 ⟷
    #: 8f30b6d): tek fark ``tests/test_flight_vehicle.py``
    #: ::test_fiziksel_olmayan_olcu_yayimlanmaz (P15B2-02'nin işaret/sıfır
    #: ayağı). İmi ``89bbee7`` (ÖH D24 hibrit a1) kaldırdı; borç GERÇEKTEN
    #: kapandı — üç motor tipinin üçü de dış çapı tek birim otoritesi
    #: ``hrma.export.motor_geometry.resolve_length_m`` ile çözüyor ve o
    #: otorite sonlu-pozitif olmayanı reddediyor. İmsiz testin kendisi bu
    #: ağaçta KOŞULDU: 6 passed (yani im kalsaydı XPASS -> kırmızı olurdu).
    #: P15B2-02'nin ikiz-sözleşme ayağı (``test_ikiz_mm_to_m_...``) HÂLÂ
    #: imli; dosya sayısı bu yüzden 22'de kaldı. Bu bir GEVŞETME DEĞİLDİR:
    #: iddia yine tam eşitliktir, yalnız tabanı kapanan borca hizalar.
    #:
    #: ÖH D26 fix-25a (6 Eylül 2026): 33 -> 34 im, 22 -> 23 dosya. Bekçi yine
    #: TAM OLARAK istediği işi yaptı; bu kez SÖKÜM değil EKLEME sessiz kalmadı.
    #: EKLENEN İM ÖLÇÜLDÜ (AST envanteri, taban 7751531): tek fark
    #: ``tests/test_mesh_disyuzey_egrilik_tabani.py``
    #: ::TestSiviVakasi::test_TESLIM_EDILEN_meshin_dis_zinciri_taban_ustunde.
    #: İmi ``d400108`` (ÖH D25 fea-cfd a1, OH-D24-01) koydu ve im BİLİNÇLİ bir
    #: BORÇ KAYDIDIR: dış yüzey eğrilik tabanının köşe düzeltme penceresi
    #: istasyon çözünürlüğüyle daralıyor (aynı konturda n_axial 128/512/1024
    #: için dış zincirin en küçük konkav yarıçapı 0,0031919 / 0,0022510 /
    #: 0,0004555 m; taban 0,002 m). Kusur OH-D24-01 onarımının ÜRÜNÜ DEĞİL:
    #: TABANDA DA VAR, onarım yalnız 512x32 yerine 1024x8 mesh teslim ederek
    #: GÖRÜNÜR KILDI. İmin kendisi bu ağaçta KOŞULDU: 1 xfailed (yani borç
    #: gerçekten açık; kusur giderilince strict im XPASS -> kırmızı verir ve
    #: kapanış yine buradan geçer). Bu bir GEVŞETME DEĞİLDİR: iddia yine tam
    #: eşitliktir, yalnız tabanı YENİ İMLENEN borca hizalar; onarım kalemi
    #: hrma/fea/mesh_axisym.py::_outer_curvature_floor_correction'dadır.
    #:
    #: ÖH D27 fix-26a (8 Eylül 2026): SAYI TABANI KALDIRILDI, yerine KÜME
    #: TABANI geldi. Neden: D26'nın kulvarları birleşince 17 im birden
    #: söküldü (34 -> 17 im, 23 -> 13 dosya) ve iki tam sayı yalnız "kaç
    #: tane" diyebildi, "hangisi" diyemedi — oysa kırmızının işi farkı
    #: ADIYLA söylemektir. Taban artık ölçüm dosyasından türetilir
    #: (``once_xpass.json`` -> ``d27_fix26a_yeniden_olcum.guncel_envanter``)
    #: ve ağaçla KÜME EŞİTLİĞİ aranır. Bu bir gevşetme değil
    #: SIKILAŞTIRMADIR: sayı eşitliği "bir im söküldü, bir im eklendi"
    #: durumunu sessizce geçirirdi, küme eşitliği geçirmez.
    #:
    #: SÖKÜLEN 17 İM ÖLÇÜLDÜ (dosya, ad, kalem kimliği, söküm commit'i:
    #: ölçüm dosyasında ``sokulen_imler``). Kapanışların KANITI: imi sökülen
    #: 17 testin tamamı (adı değişenler yeni adıyla) bu ağaçta koşuldu, 34
    #: düğümün 34'ü PASSED — imler kalsaydı XPASS(strict) verip süiti
    #: kırmızıya çevirirlerdi. Söküm commit'leri: 7de6075d (termo-ucus,
    #: P4B4-14/-16, P14M2-03), 65849d68 (sivi a2, P4B4-08), a7c836c6
    #: (altyapi, P13B1-04), fb3bb476 (kati a2, P2B1-03/P2B3-03), a201eeed
    #: (ihracat, P15B4-01), 6b54702b (bekci-cevirisi, OH-B4-03), 18216cc6
    #: (hibrit, P14M2-05), da0797d4 (app-api a5, P15B2-02), aabdcdcd
    #: (yapisal-sistem, P5B2-05/-06/-23, P5B4-31/-33).
    #:
    #:
    #: ÖH D27 fix-27a (8 Eylül 2026): TABAN D27 BİRLEŞMESİNE HİZALANDI.
    #: Ölçüt DEĞİŞMEDİ (küme eşitliği; fix-26a'nın kendi betiği
    #: ``docs/scofield/raw/OH/D27/fix26/a/betikler/olcum_xpass.py`` ile
    #: yeniden ölçüldü), yalnız blok ``d27_fix27a_yeniden_olcum`` oldu.
    #: ÖLÇÜLDÜ: 17 -> 12 im, 13 -> 12 dosya; 6 SÖKÜM + 1 EKLEME.
    #:
    #: SÖKÜLEN 6 İM (dosya, ad, kimlik, söküm commit'i tabloda):
    #: ``0dbc149a`` (arayuz a2) analysis_dock termal ekseni (OH-B3-02 /
    #: P5B2-12) ve i18n çeviri borcunu (P13B4-07); ``688724d0`` (app-api
    #: a3) S1 dürüstlük alanlarını (P13B4-05); ``d44f9548`` (hibrit a1)
    #: S2 zarf bayrağını (P13B4-04); ``b0fb49ef`` (katı a2) S5 künye
    #: zarfının İKİ imini (P13B4-03). Kapanışların KANITI: imi sökülen 6
    #: testin sahibi 7 düğüm bu ağaçta ADIYLA koşuldu, 7 PASSED — imler
    #: kalsaydı XPASS(strict) verirlerdi.
    #:
    #: EKLENEN 1 İM: ``tests/test_d15_ui_paneller_a1.py``
    #: ::test_patlama_kunyesi_panel_okuyucusunda (P5B2-05), ``cd54dc5b``
    #: (ÖH D27 fix-26b). BİLİNÇLİ borç kaydıdır: patlama mesafesi
    #: künyesini (basis + ölçekli mesafe) panel okuyucusu basmıyor.
    #: İm bu ağaçta 1 xfailed verir, yani borç gerçekten AÇIK.
    #:
    #: ÖH D28 fix-28a (9 Eylül 2026): TABAN D28 BİRLEŞMESİNE HİZALANDI.
    #: Ölçüt DEĞİŞMEDİ (küme eşitliği; fix-26a'nın kendi betiği
    #: ``docs/scofield/raw/OH/D27/fix26/a/betikler/olcum_xpass.py`` ile
    #: yeniden ölçüldü), yalnız blok ``d28_fix28a_yeniden_olcum`` oldu.
    #: ÖLÇÜLDÜ: 12 -> 12 im, 12 -> 12 dosya; 1 SÖKÜM + 1 EKLEME. SAYI
    #: DEĞİŞMEDİ — tam bu yüzden sayı eşitliği yetmez; küme eşitliği
    #: takasın iki ucunu da ADIYLA gösterdi (D20'nin öngördüğü durum).
    #:
    #: SÖKÜLEN 1 İM: ``tests/test_d15_ui_paneller_a1.py``
    #: ::test_patlama_kunyesi_panel_okuyucusunda (P5B2-05), ``2e471de7``
    #: (ÖH D28 arayuz a1, OH-D27-16). BORÇ KAPANDI: panel okuyucusu
    #: (addBlastRow) künye adlarını artık basıyor (ölçüm 0 -> 2). KANIT:
    #: imsiz test bu ağaçta koşuldu, 1 PASSED — im kalsaydı XPASS(strict)
    #: ile süiti kırmızıya çevirirdi.
    #:
    #: EKLENEN 1 İM: ``tests/test_d28_fea_cfd_a2.py``
    #: ::test_mass_breakdown_yalniz_kutle_tasir (P15B4-12), ``14463b19``
    #: (ÖH D28 fea-cfd a2). BİLİNÇLİ borç kaydı ve ENGELLİ: onarım sahası
    #: ``hrma/export/cad_visualization.py`` ihracat kulvarınındır
    #: (kardeş-dal kuralı), kalem ihracata devredildi. Kusur ölçüldü
    #: (5 kütle-olmayan sayısal alan); im bu ağaçta 1 xfailed verir.
    #:
    #: ÖH D29 ihracat a1 (9 Eylül 2026, OH-D28-07): BORÇ ÖDENDİ, blok
    #: ``d29_ihracat_a1_yeniden_olcum`` oldu. ÖLÇÜLDÜ: 12 -> 11 im,
    #: 12 -> 11 dosya; 1 SÖKÜM + 0 EKLEME.
    #:
    #: SÖKÜLEN 1 İM: ``tests/test_d28_fea_cfd_a2.py``
    #: ::test_mass_breakdown_yalniz_kutle_tasir (P15B4-12). D28'de kalem
    #: ENGELLİYDİ (ürün dosyası ``hrma/export/cad_visualization.py``
    #: ihracat kulvarınındır, kardeş-dal kuralı); D29'da sahibi onardı.
    #: ``mass_breakdown``ın 5 kütle-olmayan sayısal alanı (3 mm + 2
    #: kg/m3) SİLİNMEDİ, künyeleriyle birlikte kendi boyut sözlüklerine
    #: taşındı (``geometry_summary`` ve yeni ``material_summary``).
    #: ÖLÇÜM 5 -> 0 (``.../OH/D29/ihracat/a1/{once,sonra}_p15b412.json``);
    #: koşum ölçümü 33 taşıma, 0 kayıp, 0 değer değişimi
    #: (``a1/{once,sonra}_yerlesim.json``). KANIT: imsiz test bu ağaçta
    #: koşuldu, PASSED — im kalsaydı XPASS(strict) süiti kırardı.
    #:
    #: ÖH D31 fix-34a (14 Eylül 2026): TABAN D30 + D31 BİRLEŞMELERİNE
    #: HİZALANDI, blok ``d31_fix34a_yeniden_olcum`` oldu. Ölçüt
    #: DEĞİŞMEDİ (küme eşitliği); ölçüm betiği
    #: ``docs/scofield/raw/OH/D31/fix34/a/olcum_xpass.py`` (D29 betiğinin
    #: aynı AST taraması; eklentisi yalnız imzadan ÖLÇÜLEN kimlikler ve
    #: önceki blokla fark). ÖLÇÜLDÜ: 11 -> 12 im, 11 -> 12 dosya;
    #: 0 SÖKÜM + 1 EKLEME.
    #:
    #: EKLENEN 1 İM: ``tests/test_d30_arayuz_panel_a1.py``
    #: ::test_supurme_alanlari_sessizce_ikame_edilmiyor (ÖK-21),
    #: ``9d96472a`` (ÖH D30 arayuz-panel a1, OH-D29-02). BİLİNÇLİ borç
    #: kaydıdır: gölgeleme söküldükten sonra kazanan
    #: ``advanced.html::runParametricAnalysis`` üç süpürme alanını
    #: (``param_start``, ``param_end``, ``param_steps``) boş/sayı olmayan
    #: girdide sessizce ``1.5`` / ``4.0`` / ``10`` ile ikame ediyor, bu
    #: yüzden sunucunun ``sweep_interval_not_supplied`` (422) kapısı HİÇ
    #: koşamıyor. Onarım ÖK-21 kapsamındadır (form katmanı ``value="X"``
    #: + ``|| X`` sökümü EN SON dalgadır) ve D30 a1'de bilerek
    #: kapatılmadı. İm bu ağaçta KOŞULDU: 1 xfailed — yani borç gerçekten
    #: AÇIK; ikame kalkınca XPASS(strict) verir ve kapanış yine buradan
    #: geçer. Bu bir GEVŞETME DEĞİLDİR: iddia yine tam küme eşitliğidir,
    #: yalnız taban YENİ İMLENEN borca hizalanmıştır.
    #:
    #: UYARI (tek kaynak): imi D31 ``arayuz-panel`` kulvarı ÖK-21
    #: sökümüyle kaldırırsa blok ELLE düzeltilmez, betikle YENİDEN
    #: ÖLÇÜLÜR.
    #:
    #: TABAN DOSYASI — tek kaynak; elle yazılı tam sayı YOK.
    OLCUM_DOSYASI = ('docs/scofield/raw/OH/D17/bekci-cevirisi/a1/'
                     'once_xpass.json')
    OLCUM_BLOGU = 'd31_panel_a2_yeniden_olcum'  # ana model 14 Eyl: panel a2 P12bS1-06 imi ödendi (a/olcum_xpass.py ile ölçüldü)

    @classmethod
    def _taban_envanteri(cls):
        """Ölçüm dosyasındaki (dosya adı, test adı) kümesi.

        Dosya yoksa ya da blok bozuksa bekçi FAIL-CLOSED düşer: taban
        okunamıyorsa "eşit" denemez.
        """
        import json
        import pathlib
        yol = (pathlib.Path(__file__).resolve().parent.parent
               / cls.OLCUM_DOSYASI)
        assert kanit_gerekli(yol).is_file(), f'XPASS taban ölçümü bulunamadı: {yol}'
        blok = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8')).get(cls.OLCUM_BLOGU)
        assert isinstance(blok, dict) and blok.get('guncel_envanter'), (
            f'{cls.OLCUM_DOSYASI} içinde '
            f'{cls.OLCUM_BLOGU}.guncel_envanter yok')
        envanter = {(k['dosya'].rsplit('/', 1)[-1], k['ad'])
                    for k in blok['guncel_envanter']}
        assert len(envanter) == len(blok['guncel_envanter']), (
            'taban envanterinde yinelenen kayıt var')
        return envanter

    @staticmethod
    def _imler():
        import ast
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent
        cikti = []
        for yol in sorted(kok.rglob('*.py')):
            metin = yol.read_text(encoding='utf-8')
            if 'xfail' not in metin:
                continue
            try:
                agac = ast.parse(metin)
            except SyntaxError:                       # pragma: no cover
                continue
            for dugum in ast.walk(agac):
                for dec in getattr(dugum, 'decorator_list', []):
                    try:
                        imza = ast.unparse(dec)
                    except Exception:                 # pragma: no cover
                        continue
                    if 'xfail' in imza and 'strict=True' in imza:
                        cikti.append((yol.name, dugum.name, imza))
        return cikti

    def test_envanter_tek_dosyaya_cokmedi(self):
        """TAM KÜME EŞİTLİĞİ: ne söküm ne ekleme sessiz olabilir (ÖK-22)."""
        taban = self._taban_envanteri()
        bugun = {(d, ad) for d, ad, _imza in self._imler()}
        sokulen = sorted(taban - bugun)
        eklenen = sorted(bugun - taban)
        assert not sokulen and not eklenen, (
            'XPASS(strict) envanteri ölçülen tabandan AYRIŞTI.\n'
            f'  SÖKÜLEN ({len(sokulen)}): {sokulen}\n'
            f'  EKLENEN ({len(eklenen)}): {eklenen}\n'
            'Söküm bilinçliyse (borç kapandı) ya da ekleme bilinçliyse '
            f'(yeni borç imlendi) {self.OLCUM_DOSYASI} içindeki '
            f'{self.OLCUM_BLOGU} bloğu ÖLÇÜMLE güncellensin; sessiz geçiş '
            'yok. Kırmızı, güncellemenin kendisidir.')
        # Türetilmiş sayılar (elle yazılı taban yok): kayıt için.
        assert len(bugun) == len(taban)
        assert len({d for d, _ad in bugun}) == len({d for d, _ad in taban})

    def test_her_strict_im_gerekce_tasiyor(self):
        """Kimliksiz im, envanterin sessizce genişlemesinin kapısıdır."""
        gerekcesiz = [(d, ad) for d, ad, imza in self._imler()
                      if 'reason' not in imza]
        assert not gerekcesiz, (
            f'gerekçesiz xfail(strict) imi: {gerekcesiz}')

    #: OH-D16-18 kalem metninin "kalan meşru xfail" diye saydığı kimlikler.
    #: ÖLÇÜLDÜ (ÖH D20, AST taraması + git arkeolojisi): bunların HİÇBİRİ
    #: bugün ``xfail(strict=True)`` imi TAŞIMIYOR; kalem metni bayat.
    #:
    #: * ``P13B4-02`` / ``P13B4-01`` — im HİÇ KONMAMIŞ. ``git log -S`` ile
    #:   tests/ altındaki tek dokunuş ``73b1bb1`` (FAZ B-3) ve orada da
    #:   yalnız METİN atfı olarak girmiş (bugün ``test_wave3_contract.py``
    #:   :1221/:1227/:1246/:1251 ve ``test_wave4a_contract.py``:996).
    #: * ``P4B1-15`` ×3 — im SÖKÜLDÜ: ``66d062c`` ("11 bayat xfail(strict)
    #:   borç imi söküldü", ürün onarımı f8269a5).
    #: * ``P4B1-02`` — im SÖKÜLDÜ: ``080149e`` (D15 fix-3 2/4).
    #: * ``P11B5-02`` — borç KAPANDI: ``f8269a5`` (Z5S PK6).
    KALEMDE_ANILAN_AMA_IMSIZ = ('P13B4-02', 'P13B4-01', 'P4B1-15',
                                'P4B1-02', 'P11B5-02')

    #: Ağaçta GERÇEKTEN imli olan borç kimlikleri (envanterden ölçüldü).
    #:
    #: ÖH D27 fix-26a: ``P13B1-04`` bu listeden ÇIKARILDI çünkü imi
    #: ``a7c836c6`` (ÖH D26 altyapi a1, OH-D25-24 + OH-B2-01) SÖKTÜ ve borç
    #: GERÇEKTEN kapandı. Kapanış ölçüldü: imli test
    #: ``tests/test_ci_kapsam_kapisi.py::test_yorumdaki_dosya_sayisi_
    #: gercekle_ayni`` idi ve yerine DAHA GÜÇLÜ bir bekçi geçti —
    #: ``TestNodeKapisiKilitli::test_yorumda_ELLE_yazilmis_dosya_sayisi_YOK``
    #: artık iş akışı yorumunda elle yazılmış dosya sayısının BULUNMAMASINI
    #: şart koşuyor (yani sayının "gerçekle aynı" olmasını beklemek yerine
    #: sayının orada olmasını yasaklıyor). Bu ağaçta koşuldu: 2 passed.
    #: Kalem metni P13B1-04 hâlâ dosyanın docstring'inde anılıyor
    #: (satır 1004/1036) — kapanış, kalemin unutulması değildir.
    #:
    #: ÖH D27 fix-27a: ``P13B4-04`` de bu listeden ÇIKARILDI çünkü imi
    #: ``d44f9548`` (ÖH D27 hibrit a1) SÖKTÜ ve borç GERÇEKTEN kapandı:
    #: tank zarfı artık blokta DEĞER olarak yayımlanıyor
    #: (``vapor_model_valid``, ``tank_saturation_band_clamped``,
    #: ``tank_model_envelope_basis``), bilgi yalnız uyarı metninde değil.
    #: İmli test ``test_fazb_serilestirici_esligi.py``
    #: ::test_s2_blowdown_adim_durumu_alan_esligi bu ağaçta koşuldu:
    #: PASSED (im kalsaydı XPASS(strict) verirdi). Kimlik aşağıdaki
    #: ``D27_FIX27A_KAPANAN``a taşındı — yeniden imlenirse kırmızı.
    AGACTA_IMLI = ('P8B2-11',)

    #: ÖH D27 fix-26a'da KAPANDIĞI ölçülen kimlikler. Ters yönde bir im
    #: belirirse (kusur geri geldi ve yeniden imlendi) bu bekçi kırmızı
    #: verir — kapanış kaydı ile ağaç arasındaki fark sessiz kalamaz.
    D27_FIX26A_KAPANAN = ('P13B1-04',)

    #: ÖH D27 fix-27a'da KAPANDIĞI ölçülen kimlikler. Ölçüt katıdır:
    #: listeye yalnız BUGÜN ağaçtaki HİÇBİR xfail(strict) imzasında
    #: geçmeyen kimlik girer. Bu yüzden ``P13B4-05`` burada YOK — s1
    #: imi ``688724d0`` ile kalktı ama aynı dosyadaki
    #: ``test_s3_termal_kayit_yayimlanan_govdeye_ulasiyor`` hâlâ o
    #: kimlikle imli; İM düzeyinde kapanış KİMLİK düzeyinde kapanış
    #: değildir ve bu ayrım sessiz geçemez.
    D27_FIX27A_KAPANAN = ('OH-B3-02', 'P5B2-12', 'P13B4-03',
                          'P13B4-04', 'P13B4-07')

    def test_agacta_imli_kimlikler_duruyor(self):
        """Ağaçta ÖLÇÜLEN imler kaybolamaz."""
        imzalar = ' | '.join(imza for _d, _ad, imza in self._imler())
        for kimlik in self.AGACTA_IMLI:
            assert kimlik in imzalar, (
                f'{kimlik} imi kayboldu; söküldüyse D15-BEKCI-04 envanteri '
                've OH-D16-18 kaydı güncellenmeliydi')

    def test_D27_kapanan_kimlikler_yeniden_imlenmedi(self):
        """Kapanış kaydı ile ağaç ayrışırsa kırmızı."""
        imzalar = ' | '.join(imza for _d, _ad, imza in self._imler())
        kapanan = tuple(self.D27_FIX26A_KAPANAN) + tuple(
            self.D27_FIX27A_KAPANAN)
        geri = [k for k in kapanan if k in imzalar]
        assert not geri, (
            f'{geri} için xfail(strict) imi yeniden BELİRDİ; oysa ÖH D27 '
            'fix-26a (a7c836c6) ve fix-27a (0dbc149a / 688724d0 / '
            'd44f9548 / b0fb49ef) bu kimliklerin borcunun kapandığını '
            'ÖLÇMÜŞTÜ. Kapanış kaydı ve envanter birlikte güncellensin')

    def test_kalemin_andigi_kimlikler_imsiz_OLDUGUNU_soyluyor(self):
        """OH-D16-18 kalem metni ile ağaç arasındaki fark SESSİZ KALAMAZ.

        Fable-D17 ŞART'ı: eski test kalemin listesini değil, ağaçta bulduğu
        BAŞKA bir kimliği (P13B4-04) çiviliyor ve rapor bunu "liste
        doğrulandı" diye sunuyordu — sessiz ikame. İki beklenti artık AYRI:
        ağaçta imli olanlar (yukarıdaki test) ve kalem metninde anılıp
        ağaçta İMSİZ olanlar (bu test). İmsizlik ölçülmüş bir GERÇEKTİR,
        eksiklik değil; ters yönde bir im BELİRİRSE kalem metni ile envanter
        yeniden hizalanmalıdır.
        """
        imzalar = ' | '.join(imza for _d, _ad, imza in self._imler())
        beklenmedik = [k for k in self.KALEMDE_ANILAN_AMA_IMSIZ
                       if k in imzalar]
        assert not beklenmedik, (
            f'{beklenmedik} için xfail(strict) imi BELİRDİ; oysa ÖH D20 '
            'ölçümü bu kimliklerin imsiz olduğunu (kimi hiç konmamış, kimi '
            'söküldü) kayda geçirmişti. Kalem metni (OH-D16-18), '
            'once_xpass.json ve bu liste birlikte güncellensin')


# ===========================================================================
# 7) P13B4-10 — KAMPANYA KRİTİKLERİNİN BEKÇİ KADEMELERİ
# ===========================================================================


def _modul_aniliyor(modul, govde):
    """Modül adı gövdede KELİME olarak geçiyor mu?

    ÖH D26 · defter **OH-D25-05** [23]: ölçüt eskiden ``modul in govde``
    idi — alt-dize. ``response`` gibi bir modül adı başka bir adın
    (``response_time``) ya da bir yorumun içinde geçtiğinde kritik D0'dan
    çıkıyordu. Kelime sınırı bu kandırmayı kapatır. ÖLÇÜLDÜ
    (``once_ohd2505.json``): 43 kritikte iki ölçüt de D0 = 0 veriyor,
    yani sıkılaştırma yeni borç doğurmadı.
    """
    return re.search(r'\b%s\b' % re.escape(modul), govde) is not None


class TestP13B410KritikBekciKademeleri:
    """54 kritiğin kaçında kusuru tanımlayan sembolü anan test var?

    P13 ölçümü (``B4-repro-13.py``, ölçüt üç kademeli):

    ==========  ====  =====
    kademe      P13   D17
    ==========  ====  =====
    D0 BEKÇİSİZ    3     0
    D1 DOLAYLI    30    30
    D2 ADAY       10    13
    ?dosya-yok    11    11
    ==========  ====  =====

    ÖH D17'de aynı betik (yalnız kök yolları bu worktree'ye çevrilerek)
    yeniden koşuldu: ``once_p13b410.json``. **D0 kapandı** — artık hiçbir
    kritiğin ürün dosyası testsiz değil; D2 (aday bekçi) 10 -> 13.

    Kalem KAPANMADI: D1 + ? = 41 kritikte hâlâ sembolü anan test yok.
    Kapanışı 41 ayrı bekçi demektir ve her biri ilgili kulvarın sahasında.
    Bu sınıf ölçümü KALICI kılar: D0 sıfırdan yukarı çıkarsa (yani bir
    ürün dosyası bütünüyle testsiz kalırsa) kırmızı verir.
    """

    D0_TAVANI = 0
    OLCULEN_TOPLAM = 54

    #: ÖH D26 · defter **OH-D25-05** [23] — D0'ın ÖLÇTÜĞÜ ŞEYİN SINIRI.
    #: D0 "bu ürün dosyasının modül adı tests/ ağacında hiç geçmiyor mu"
    #: sorusudur; **"bekçili mi"** sorusu DEĞİLDİR. Fable-D20 bunu adıyla
    #: saydı: ölçüt alt-dize tabanlıydı, yani modül adının bir YORUMDA ya
    #: da başka bir adın parçası olarak geçmesi kritiği D0'dan çıkarıyordu.
    #: İki şey yapıldı:
    #:   (a) ölçüt kelime sınırına çekildi (``_modul_aniliyor``). ÖLÇÜLDÜ
    #:       (``once_ohd2505.json``): 43 kritikte alt-dize D0 = 0, kelime
    #:       sınırıyla da D0 = 0 — sıkılaştırma yeni borç doğurmadı, ama
    #:       ölçüt artık "ismi bir yorumda geçiyor" ile kandırılamaz.
    #:   (b) ölçütün sınırı SAYIYLA ilan edildi: kritiklerin kaçının ürün
    #:       modülü tests/ tarafından gerçekten İTHAL EDİLİYOR. ÖLÇÜLDÜ:
    #:       43 kritiğin **17**'sinin modülü hiçbir testte ithal edilmiyor
    #:       (yalnız adı geçiyor). Bu sayı tek yönlü mandaldır: büyürse
    #:       kırmızı verir, küçülürse ADIYLA güncellenir.
    ITHAL_EDILMEYEN_TAVANI = 17

    @staticmethod
    def _ithal_edilen_modul_adlari():
        """tests/ ağacında ithal edilen modül/ad kümesi (AST'ten)."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent
        adlar = set()
        for yol in sorted(kok.rglob('*.py')):
            if '__pycache__' in yol.parts:
                continue
            try:
                agac = ast.parse(yol.read_text(encoding='utf-8',
                                               errors='replace'))
            except SyntaxError:                           # pragma: no cover
                continue
            for d in ast.walk(agac):
                if isinstance(d, ast.Import):
                    for a in d.names:
                        adlar.update(a.name.split('.'))
                elif isinstance(d, ast.ImportFrom):
                    if d.module:
                        adlar.update(d.module.split('.'))
                    for a in d.names:
                        adlar.add(a.name)
        return adlar

    def test_D0_olcutu_ithal_kademesiyle_sinirli(self, kritikler):
        """D0=0, "hepsi bekçili" DEMEK DEĞİL — sınır sayıyla duruyor.

        OH-D25-05 [23]: D0 yalnız "adı hiç anılmıyor" ölçüsüdür. Bir
        kademe daha sıkı ölçüt (ürün modülü tests/ tarafından İTHAL
        EDİLİYOR mu) bugün 17 kritikte olumsuz. Bu iddia o borcun
        büyümesini yasaklar; kapanışı 17 ayrı bekçi demektir ve her biri
        ilgili kulvarın sahasındadır.
        """
        ithaller = self._ithal_edilen_modul_adlari()
        ithalsiz = sorted(
            kid for kid, k in kritikler.items()
            if k.get('dosya')
            and pathlib.Path(k['dosya']).stem
            and pathlib.Path(k['dosya']).stem not in ithaller)
        assert len(ithalsiz) <= self.ITHAL_EDILMEYEN_TAVANI, (
            'ürün modülü hiçbir testte İTHAL EDİLMEYEN kritik sayısı '
            f'{len(ithalsiz)} > tavan {self.ITHAL_EDILMEYEN_TAVANI}: '
            f'{ithalsiz}')
        assert len(ithalsiz) == self.ITHAL_EDILMEYEN_TAVANI, (
            f'borç KÜÇÜLDÜ ({len(ithalsiz)}); ITHAL_EDILMEYEN_TAVANI aşağı '
            'çekilsin (mandal tek yönlüdür, sessiz gevşeme yok)')

    @staticmethod
    def _tests_govdesi():
        """tests/ ağacının TAMAMI — D0 ölçütünün aradığı yer."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent
        parca = []
        for yol in sorted(kok.rglob('*.py')):
            if '__pycache__' in yol.parts:
                continue
            parca.append(yol.read_text(encoding='utf-8', errors='replace'))
        return '\n'.join(parca)

    @pytest.fixture(scope='class')
    def kritikler(self):
        """Kampanya kritik tablosu (ölçümün GİRDİSİ, hükmü değil)."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent.parent
        yol = (kok / 'docs/scofield/raw/P13/'
               'B4-cikti-12-kritikler.json')
        assert kanit_gerekli(yol).is_file(), (
            'kampanya kritik tablosu bu ağaçta yok; D0 ölçütü ÖLÇÜLEMEZ '
            '(ölçülemeyen "temiz" değildir)')
        return json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))

    @pytest.fixture(scope='class')
    def olcum(self):
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent.parent
        kanit = (kok / 'docs/scofield/raw/OH/D17/bekci-cevirisi/a1'
                 / 'once_p13b410.json')
        if not kanit_gerekli(kanit).is_file():                       # pragma: no cover
            pytest.skip('P13B4-10 ölçüm kaydı bu ağaçta yok')
        return json.loads(kanit_gerekli(kanit).read_text(encoding='utf-8'))

    def test_olcum_kaydi_54_kritigi_kapsiyor(self, olcum):
        assert len(olcum) == self.OLCULEN_TOPLAM
        assert {s['id'] for s in olcum}.__len__() == self.OLCULEN_TOPLAM

    def test_D0_bekcisiz_kritik_kalmadi(self, kritikler):
        """CANLI AĞAÇ ölçümü — dondurulmuş kayıt değil (Fable-D17 ŞART'ı).

        Eski hâli ``once_p13b410.json``'u okuyordu: bir ürün dosyasının
        BÜTÜN testleri silinse JSON değişmez, bekçi yeşil kalırdı — kayıt
        kilidi, ağaç kilidi değil. Şimdi ``olcum_p13b410.py``'nin D0
        ölçütü (kritiğin ürün dosyasının modül adı tests/ altında hiç
        geçmiyor mu) BURADA, canlı ağaç üstünde yeniden koşuluyor.
        """
        govde = self._tests_govdesi()
        d0 = []
        for kid, k in kritikler.items():
            dosya = k.get('dosya', '')
            if not dosya:
                continue                      # '?dosya-yok' — D0 değil
            modul = pathlib.Path(dosya).stem
            if modul and not _modul_aniliyor(modul, govde):
                d0.append(kid)
        assert len(d0) <= self.D0_TAVANI, (
            'ürün dosyasını HİÇBİR test anmayan kritik geri geldi '
            f'(CANLI ölçüm): {sorted(d0)}')

    def test_kayit_canli_agacla_ayni_D0_diyor(self, olcum, kritikler):
        """Dondurulmuş kayıt ile canlı ağaç ayrışırsa kayıt bayattır."""
        kayit_d0 = {s['id'] for s in olcum if s['kademe'].startswith('D0')}
        govde = self._tests_govdesi()
        canli_d0 = {
            kid for kid, k in kritikler.items()
            if k.get('dosya')
            and not _modul_aniliyor(pathlib.Path(k['dosya']).stem, govde)}
        assert kayit_d0 == canli_d0, (
            f'kayıt D0={sorted(kayit_d0)} ⟷ canlı D0={sorted(canli_d0)}; '
            'once_p13b410.json yenilensin')

    def test_kalan_borc_ADIYLA_sayiliyor(self, olcum):
        """Kalem kapanmadı; kalan borç gizlenmiyor, sayılıyor."""
        d1 = [s['id'] for s in olcum if s['kademe'].startswith('D1')]
        belirsiz = [s['id'] for s in olcum if s['kademe'].startswith('?')]
        assert len(d1) + len(belirsiz) == 41, (
            'kalan borç sayısı değişti; ölçüm yenilenip kalem notu '
            f'güncellensin: D1={len(d1)} ?={len(belirsiz)}')
        # D2 "kilitliyor" demek DEĞİL — yalnız aday. Bu kilit o ayrımı korur.
        d2 = [s['id'] for s in olcum if s['kademe'].startswith('D2')]
        assert len(d2) == 13
