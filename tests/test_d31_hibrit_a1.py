"""ÖH D31 · hibrit a1 — dört kalemin bekçisi.

Kalemler ve ölçümleri (``docs/scofield/raw/OH/D31/hibrit/a1/once.json`` ->
``sonra.json``; taban 9d70e9ed):

OH-D26-04  Soğutma menüsünde ``radial`` ile ``spiral`` BİREBİR aynı sayıları
           üretiyordu (8.337 ortak yaprağın 8.335'i aynı, FİZİK yaprağı farkı
           0) ve yanıtta bunu söyleyen tek yaprak yoktu: kullanıcının kelimesi
           6 yaprakta geri okunuyor, hiçbir sayıya girmiyordu. Onarım kanal
           geometrisi MODELİ yazmaz (girdileri üründe toplanmıyor; uydurma
           yasak) — modellenmediğini MAKİNE-OKUR biçimde söyler.
P12bB3-02  Menüde ``disabled`` duran dört yakıt anahtarı (``carbon``,
           ``al2o3``, ``mixture``, ``custom``) dördü de AYNI genel gerekçeyle
           reddediliyordu (ayrı gerekçe sayısı 1). Üçü ayrı şeydir: kategori
           hatası / literatür borcu / şema borcu. Onarım hiçbir yakıt AÇMAZ,
           reddin sebebini adlandırır.
OH-B1-05   Yanlılık uyarısı TEK sayı yayımlıyordu (−%39,5) ve o sayı bağımsız
           ölçümün kampanya gövdesinin (−%50,6 … −%41,8) DIŞINDAYDI. Onarım
           katsayıya DOKUNMAZ; kazanılmamış kesinlik iddiasını kaldırır.
OH-D21-04  ``abs`` ile ``htpb`` birebir aynı (a, n) çiftini taşıyor; künye veri
           katmanında "BORROWED" diyor ama ABS seçen kullanıcının koşusunda
           bunu söyleyen uyarı YOKTU.

ASTRA UYARISI (14 Eylül 2026) burada MAKİNEYE BAĞLIDIR: yayımlanan kampanya
gövdesinin her satırı HTPB/N₂O olmalıdır. Zilliac & Karabeyoglu 2006 Tablo 2
satırları OKSİJEN deneyleridir ve N2O katsayısını çürütemez; bu bekçi onların
beyana sızmasını kırmızıya çevirir.
"""

import ast
import contextlib
import io
from pathlib import Path

import pytest

from hrma.engines.hybrid_rocket_engine import (
    COOLING_CHANNEL_TO_TYPE,
    COOLING_GEOMETRY_EQUIVALENCE,
    COOLING_CHANNEL_GEOMETRY_SELECTIONS,
    HTPB_INDEPENDENT_CAMPAIGNS,
    HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT,
    HybridRocketEngine,
)
from hrma.engines.combustion_analysis import (
    HYBRID_FUEL_REJECTION_REASONS,
    SUPPORTED_HYBRID_FUEL_KEYS,
    CombustionAnalyzer,
)
from hrma.data.propellant_database import (
    HYBRID_REGRESSION_COEFFICIENTS, HYBRID_REGRESSION_SOURCES)


KOK = Path(__file__).resolve().parents[1]
YANMA_PY = KOK / 'hrma' / 'engines' / 'combustion_analysis.py'


def _fonksiyon_dugumu(yol: Path, ad: str):
    """Fonksiyonun AST düğümünü DOSYADAN okur (OH-D33-10).

    ``inspect.getsource`` satır numarasını içe aktarılmış kod nesnesinden
    alır ve metni ``linecache``ten çeker; dosya içe aktarmadan SONRA
    değişirse (birleşme, yeniden taban) kaymış satırlar döner ve bekçi
    SAHTE KIRMIZI verir. Taban kaydı-15 dersi, 14 Eylül fix-34b: main
    ağacında beş bekçi tam bu kanaldan kırmızı olmuştu. Dosyayı o an
    okuyup AST ile ayrıştırmak kanalı kapatır: satır numarası hiç
    kullanılmaz, düğüm ADIYLA bulunur. İDDİA DEĞİŞMEDİ, değişen yalnız
    okuma yoludur.

    Emsal: ``tests/test_d33_bekci_cevirisi_a1.py::_fonksiyon_kaynagi``,
    ``tests/test_d33_app_api_uc_a1.py::test_kural_IKINCI_kez_yazilmadi``.
    """
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    for dugum in ast.walk(agac):
        if (isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef))
                and dugum.name == ad):
            return dugum
    return None


TEMEL = dict(of_ratio=2.5, chamber_pressure=20, atmospheric_pressure=1.0,
             fuel_type='htpb', oxidizer_type='n2o', thrust=1000,
             burn_time=10)


def _kos(**kw):
    ayar = dict(TEMEL)
    ayar.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        motor = HybridRocketEngine(**ayar)
        return motor, motor.calculate()


def _uyari(sonuc, kod):
    for u in (sonuc.get('warnings') or []):
        if isinstance(u, dict) and u.get('code') == kod:
            return u
    return None


def _yapraklar(x, yol=''):
    if isinstance(x, dict):
        for k in sorted(x, key=str):
            yield from _yapraklar(x[k], '%s.%s' % (yol, k))
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            yield from _yapraklar(v, '%s[%d]' % (yol, i))
    else:
        yield yol, repr(x)


@pytest.fixture(scope='module')
def radial():
    return _kos(cooling_type='radial')


@pytest.fixture(scope='module')
def spiral():
    return _kos(cooling_type='spiral')


@pytest.fixture(scope='module')
def htpb():
    return _kos()


@pytest.fixture(scope='module')
def abs_motoru():
    return _kos(fuel_type='abs')


# ===========================================================================
# OH-D26-04 — kanal geometrisi modellenmiyor, bu ADIYLA söyleniyor
# ===========================================================================

class TestOhD2604KanalGeometrisi:

    def test_esdeger_sinif_elle_yazilmaz_eslemeden_turetilir(self):
        """Doktrin 4: beyan ikinci bir liste taşımaz, eşlemeden türer."""
        beklenen = {}
        for k in COOLING_CHANNEL_TO_TYPE:
            if k == COOLING_CHANNEL_TO_TYPE[k]:
                continue        # ısı-transferi teriminin kendisi
            beklenen.setdefault(COOLING_CHANNEL_TO_TYPE[k], []).append(k)
        beklenen = {s: tuple(sorted(v)) for s, v in beklenen.items()}
        assert COOLING_GEOMETRY_EQUIVALENCE == beklenen, (
            'Denklik sınıfı COOLING_CHANNEL_TO_TYPE ile ayrışmış: menüye yeni '
            'bir geometri eklenip beyan güncellenmemiş olabilir.')
        assert set(COOLING_CHANNEL_GEOMETRY_SELECTIONS) == {
            k for k in COOLING_CHANNEL_TO_TYPE
            if k != COOLING_CHANNEL_TO_TYPE[k]}

    def test_ayni_sinifa_dusen_iki_secim_not_modelled_ilan_edilir(self,
                                                                 radial):
        _, sonuc = radial
        blok = sonuc.get('cooling_channel_geometry')
        assert blok, (
            'cooling_channel_geometry bloğu yok: kullanıcı kanal geometrisi '
            'seçiyor, yanıt onun hiçbir sayıya girmediğini söylemiyor '
            '(OH-D26-04 ölçümü: radial|spiral FİZİK yaprağı farkı 0).')
        assert blok['requested'] == 'radial'
        assert blok['resolved_class'] == 'regenerative'
        assert blok['modelled'] is False
        assert blok['status'] == 'NOT_MODELLED'
        assert 'spiral' in blok['indistinguishable_from']
        # Eksik girdiler ADIYLA: neyin olmadığı gizlenmez.
        assert blok['missing_inputs_for_geometry_model'], (
            'geometri modeli için eksik girdiler adlandırılmamış')

    def test_uyari_kelimeyi_geri_okurken_modellenmedigini_de_soyler(
            self, radial):
        _, sonuc = radial
        u = _uyari(sonuc, 'warn.hybrid.cooling_channels_assumed')
        assert u, 'rejeneratif seçimde soğutma uyarısı hiç doğmuyor'
        p = u['params']
        assert p['geometry'] == 'radial'
        assert p['geometry_modelled'] is False, (
            'Uyarı kullanıcının kelimesini geri okuyor ama o kelimenin '
            'hiçbir sayıya girmediğini SÖYLEMİYOR — ölçülen kusur buydu.')
        assert p['resolved_class'] == 'regenerative'
        assert 'spiral' in p['indistinguishable_from']

    def test_radial_ile_spiral_arasinda_FIZIK_yapragi_ayrismiyor(
            self, radial, spiral):
        """Beyanın kendisi ÖLÇÜLÜR: ayrışan her yaprak bir BEYAN yaprağıdır.

        Bu bekçi kusuru KİLİTLEMEZ: bir gün geometri gerçekten modellenirse
        fizik yaprakları ayrışır ve testin beklentisi de (blok
        ``modelled=True`` döneceği için) birlikte güncellenir — aşağıdaki
        ilk assert o günü zorunlu kılar.
        """
        _, s_rad = radial
        _, s_spi = spiral
        d_rad = dict(_yapraklar(s_rad))
        d_spi = dict(_yapraklar(s_spi))
        assert s_rad['cooling_channel_geometry']['modelled'] is False
        farkli = [y for y in sorted(set(d_rad) & set(d_spi))
                  if d_rad[y] != d_spi[y]]
        beyan = [y for y in farkli
                 if ('cooling_channel_geometry' in y
                     or 'params.geometry' in y
                     or 'indistinguishable_from' in y)]
        assert set(farkli) == set(beyan), (
            'radial ile spiral arasında BEYAN DIŞI yaprak ayrışıyor: %r. '
            'Ya geometri artık modelleniyor (o zaman blok modelled=True '
            'demeli ve bu bekçi güncellenmeli) ya da sessiz bir sapma var.'
            % sorted(set(farkli) - set(beyan))[:10])
        assert farkli, ('hiçbir yaprak ayrışmıyor: kullanıcının seçimi '
                        'yanıtta hiç izlenemiyor')

    def test_tek_secimli_sinif_not_modelled_denmez(self):
        """``none`` kendi sınıfında yalnızdır: ayırt edilecek bir şey yok."""
        _, sonuc = _kos(cooling_type='none')
        blok = sonuc['cooling_channel_geometry']
        assert blok['indistinguishable_from'] == ()
        assert blok['modelled'] is True
        assert blok['status'] == 'CLASS_ONLY'


# ===========================================================================
# P12bB3-02 — reddin gerekçesi ADIYLA
# ===========================================================================

class TestP12bB302RedGerekcesi:

    @staticmethod
    def _reddet(yakit):
        ca = CombustionAnalyzer()
        with pytest.raises(ValueError) as tutam:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                ca._calculate_elemental_composition({yakit: 100.0}, 'n2o', 2.5)
        return tutam.value

    def test_dort_anahtar_uc_ayri_gerekce_veriyor(self):
        gerekceler = {y: getattr(self._reddet(y), 'reason', None)
                      for y in ('al2o3', 'carbon', 'mixture', 'custom')}
        assert gerekceler == {
            'al2o3': 'not_a_fuel',
            'carbon': 'no_peer_reviewed_correlation',
            'mixture': 'no_request_contract',
            'custom': 'no_request_contract',
        }, gerekceler
        assert len(set(gerekceler.values())) == 3, (
            'ÖLÇÜLEN kusur: dördü de AYNI genel gerekçeyi alıyordu '
            '(ayrı gerekçe sayısı 1). Üçü ayrı şeydir.')

    def test_her_red_alan_adi_ve_aciklama_tasir(self):
        for yakit in ('al2o3', 'carbon', 'mixture', 'custom'):
            e = self._reddet(yakit)
            assert e.field == 'fuel_type'
            assert getattr(e, 'explanation', None), (
                '%s reddi gerekçeyi makine-okur alanla taşımıyor' % yakit)
            assert e.supported_fuels == list(SUPPORTED_HYBRID_FUEL_KEYS)

    def test_tablodaki_hicbir_anahtar_sessizce_acilmadi(self):
        """FAIL-CLOSED korunur: adlandırma bir yakıt AÇMAZ."""
        assert not (set(HYBRID_FUEL_REJECTION_REASONS)
                    & set(SUPPORTED_HYBRID_FUEL_KEYS)), (
            'Gerekçe tablosundaki bir anahtar desteklenen kümeye sızmış: '
            'red gerekçesi yazmak yakıt açmak değildir.')
        assert set(SUPPORTED_HYBRID_FUEL_KEYS) == {
            'htpb', 'paraffin', 'pe', 'pmma', 'abs', 'pla', 'aluminum'}, (
            'Desteklenen yakıt kümesi değişmiş. Bu kalemin onarımı hiçbir '
            'yakıt açmaz; yeni yakıt ayrı bir VERİ kararıdır.')

    def test_tablonun_disindaki_anahtar_genel_gerekceyi_alir(self):
        e = self._reddet('kerosene')
        assert e.reason == 'unsupported_fuel_key'
        assert getattr(e, 'explanation', None) is None

    def test_ikinci_kapi_da_ayni_gerekceyi_veriyor(self):
        """Stokiyometri kapısı (``of_stoich``) ile elemental kapı TEK KAYNAK."""
        ca = CombustionAnalyzer()
        with pytest.raises(ValueError) as tutam:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                ca._calculate_stoichiometric_of({'al2o3': 100.0}, 'n2o')
        assert tutam.value.reason == 'not_a_fuel'


# ===========================================================================
# OH-B1-05 — tek yanlılık sayısı tek başına yayımlanmaz
# ===========================================================================

class TestOhB105YanlilikGovdesi:

    def test_uc_kampanya_ADIYLA_yayimlaniyor(self, htpb):
        _, sonuc = htpb
        u = _uyari(sonuc, 'warn.hybrid.htpb_coeff_bias')
        assert u, 'yanlılık uyarısı doğmuyor'
        p = u['params']
        adlar = [k['campaign'] for k in p['independent_campaigns']]
        assert adlar == ['Rezaei 2018', 'Carmicino 2013', 'Heydari 2017'], adlar
        # ÖH D32 fix-35d — YAYIMLANAN KAP JSON'UN KENDİ KABIDIR.
        # Sabit (``HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT``) demet olarak
        # DURUR (değişmezlik); yayımlanan kayıt JSON'a indirgenir, çünkü
        # JSON'da demet yoktur ve gövde gidiş-dönüşte liste olarak geri
        # geliyordu (taban kırmızısı ``test_sonuc_json_serilestirilebilir``).
        # İDDİA GÜÇLENDİ: hem kap tipi hem sayılar sınanıyor.
        assert p['independent_campaign_bias_band_pct'] == [-50.6, -41.8]
        assert isinstance(p['independent_campaign_bias_band_pct'], list), (
            'yayımlanan bant JSON-yerli olmayan bir kapta: %r'
            % (p['independent_campaign_bias_band_pct'],))

    def test_tek_sayi_TEK_BASINA_cikmiyor(self, htpb):
        """ÖLÇÜLEN kusur: params yalnız {bias_pct, medape_pct} idi."""
        _, sonuc = htpb
        p = _uyari(sonuc, 'warn.hybrid.htpb_coeff_bias')['params']
        assert 'bias_pct' in p
        eksik = {'independent_campaigns', 'independent_pool_points',
                 'own_pool_points', 'reconciled',
                 'unreconciled_reasons'} - set(p)
        assert not eksik, (
            'Yanlılık beyanı kazanılmamış bir kesinlik iddiası taşıyor: '
            'eksik alanlar %r' % sorted(eksik))
        assert p['reconciled'] is False, (
            'reconciled=True iddia ediliyor. İki ölçüm UZLAŞTIRILDIYSA '
            'ölçümü yaz (hangi havuz, hangi akı kapanışı) ve '
            'tests/test_hibrit_sure_cf.py içindeki xfail borç imini AYNI '
            'commit\'te kaldır.')
        assert len(p['unreconciled_reasons']) >= 2

    def test_ASTRA_yayimlanan_her_kampanya_N2O_dur(self, htpb):
        """Zilliac & Karabeyoglu Tablo 2 OKSİJEN'dir; beyana sızamaz.

        Kaynak/oksitleyici eşleşmeden bir kampanya HTPB/N₂O katsayısı
        hakkında kanıt sayılmaz (Astra uyarısı, 14 Eylül 2026).
        """
        _, sonuc = htpb
        p = _uyari(sonuc, 'warn.hybrid.htpb_coeff_bias')['params']
        for k in p['independent_campaigns']:
            assert k['oxidizer'] == 'n2o', (
                '%r oksitleyicisi %r olan bir kampanya HTPB/N₂O yanlılık '
                'beyanına girmiş: farklı oksitleyicinin katsayısı bu iddiayı '
                'ne doğrular ne çürütür.' % (k['campaign'], k['oxidizer']))
        for k in HTPB_INDEPENDENT_CAMPAIGNS:
            assert k['oxidizer'] == 'n2o'

    def test_kampanya_govdesi_yayimlanan_sayiyi_KAPSAMIYOR(self):
        """Açık borç GÖRÜNÜR kalır: −%39,5 gövdenin dışındadır.

        Bu bir kusurun kilidi değil, kusurun ÖLÇÜSÜDÜR: gövde ürünün
        beyanını kapsar hâle gelirse (katsayı ya da ölçüm değişirse) test
        kırmızı verir ve borç iminin kaldırılmasını zorlar.
        """
        alt, ust = HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT
        from hrma.engines.hybrid_rocket_engine import HTPB_COEFF_DB_BIAS_PCT
        assert not (alt <= HTPB_COEFF_DB_BIAS_PCT <= ust), (
            'Ürünün yayımladığı yanlılık artık bağımsız kampanya gövdesinin '
            'İÇİNDE: iki ölçüm uzlaşmış olabilir. Uzlaşmayı yaz, '
            'reconciled bayrağını ve test_hibrit_sure_cf.py xfail imini '
            'AYNI commit\'te güncelle.')

    def test_katsayi_DEGISMEDI(self):
        """Bu kalem beyanı onarır, katsayıya DOKUNMAZ (kaynak borcu)."""
        assert HYBRID_REGRESSION_COEFFICIENTS['htpb'] == {
            'a': 3.68e-5, 'n': 0.555}


# ===========================================================================
# OH-D21-04 — ödünç (a, n) çifti kullanıcıya söylenir
# ===========================================================================

class TestOhD2104OduncKatsayi:

    def test_abs_kosusunda_odunc_bildirimi_var(self, abs_motoru):
        _, sonuc = abs_motoru
        u = _uyari(sonuc, 'warn.hybrid.regression_coeff_borrowed')
        assert u, (
            'ABS seçen kullanıcı HTPB/N₂O çiftiyle koşuyor ve bunu söyleyen '
            'tek bir uyarı yok (ölçüldü: once.json K4).')
        p = u['params']
        assert p['fuel'] == 'abs'
        # ÖH D32 fix-35d: yayımlanan kap JSON-yerlidir (bkz. yukarıdaki
        # bant bekçisi); ödünç verenlerin KİMLİĞİ ve SIRASI değişmedi.
        assert p['borrowed_from'] == ['htpb'], p['borrowed_from']
        assert isinstance(p['borrowed_from'], list), p['borrowed_from']
        assert p['independent_fit'] is False
        assert 'Whitmore' in (p['citation'] or '')

    def test_bagimsiz_katsayili_yakitta_uyari_susar(self, htpb):
        _, sonuc = htpb
        assert _uyari(sonuc, 'warn.hybrid.regression_coeff_borrowed') is None

    def test_veren_yakit_ELLE_YAZILMAZ_katalogdan_turer(self, abs_motoru):
        _, sonuc = abs_motoru
        p = _uyari(sonuc, 'warn.hybrid.regression_coeff_borrowed')['params']
        c_abs = HYBRID_REGRESSION_COEFFICIENTS['abs']
        beklenen = tuple(sorted(
            ad for ad, c in HYBRID_REGRESSION_COEFFICIENTS.items()
            if ad != 'abs' and (c['a'], c['n']) == (c_abs['a'], c_abs['n'])
            and HYBRID_REGRESSION_SOURCES[ad]['independent']))
        # Kaynak sabiti demet üretir; yayımlanan kayıt JSON-yerli listedir.
        assert p['borrowed_from'] == list(beklenen)

    def test_KUNYESIZ_ikizlik_yasak(self):
        """Aynı (a, n) çiftini taşıyan iki yakıt künyeyle açıklanmalı.

        İkizlik yasak değil; künyesiz ikizlik yasaktır. Biri sessizce
        üçüncü bir ikiz eklerse bu bekçi kırmızı verir.
        """
        adlar = sorted(HYBRID_REGRESSION_COEFFICIENTS)
        for i, x in enumerate(adlar):
            for y in adlar[i + 1:]:
                cx = HYBRID_REGRESSION_COEFFICIENTS[x]
                cy = HYBRID_REGRESSION_COEFFICIENTS[y]
                if (cx['a'], cx['n']) != (cy['a'], cy['n']):
                    continue
                bagimsiz = [
                    ad for ad in (x, y)
                    if HYBRID_REGRESSION_SOURCES[ad]['independent']]
                assert len(bagimsiz) <= 1, (
                    '%s ile %s birebir aynı (a, n) çiftini taşıyor ve İKİSİ '
                    'de künyesinde "independent: True" diyor. En az biri '
                    'ödünç alandır; künyesi bunu söylemeli.' % (x, y))


# ===========================================================================
# P15B2-01 (OH-D30-08 dağıtımı, satır 31) — yerel değer kapısı merkeze bağlı
# ===========================================================================

class TestP15B201GammaKapisi:
    """``gamma_is_physical`` sayı okuma kuralını MERKEZDEN alıyor.

    Borç metni: "bu yerel DEĞER kapısı hrma.utils.input_guard merkezine
    BAĞLI DEĞİL: aynı kötü girdi modüle göre reddediliyor / sessiz None /
    varsayılan oluyor". Onarım davranışı DEĞİŞTİRMEZ (aynı 12 girdide aynı
    12 yanıt); kuralın tek kaynaktan gelmesini sağlar ve sembolü DOĞRUDAN
    sınayan bekçiyi ekler (borç metninin ikinci şartı).
    """

    def test_kapi_merkezi_input_guard_kullaniyor(self):
        """Ölçüt DOSYADAN, AST ile okunur (OH-D33-10).

        Eskiden kaynak ``inspect.getsource`` ile alınırdı; o yol satır
        numarasına bağlıdır ve birleşmeyle kirlenen ağaçta kayar (taban
        kaydı-15). Sorulan şey AYNI kaldı: sayı okuma kuralı
        ``gamma_is_physical``in GÖVDESİNDE mi yazıyor, yoksa merkezden
        mi geliyor.
        """
        from hrma.engines import combustion_analysis as ca
        dugum = _fonksiyon_dugumu(YANMA_PY, 'gamma_is_physical')
        assert dugum is not None, (
            'gamma_is_physical %s içinde bulunamadı: bekçi ÖLÇEMEDİ '
            '(fail-closed)' % YANMA_PY)
        adlar = {d.id for d in ast.walk(dugum) if isinstance(d, ast.Name)}
        assert '_finite_number' in adlar, (
            'gamma_is_physical sayı okumasını hâlâ kendi içinde yazıyor; '
            'hrma.utils.input_guard merkezine bağlı değil (P15B2-01).')
        from hrma.utils.input_guard import finite_number
        assert ca._finite_number is finite_number

    @pytest.mark.parametrize('deger,beklenen', [
        (1.2, True), (1.4, True), (1.999, True),
        (1.0, False), (2.0, False), (0.5, False), (2.5, False),
        ('1.3', True), ('abc', False), (None, False),
        (float('nan'), False), (float('inf'), False),
    ])
    def test_band_davranisi_degismedi(self, deger, beklenen):
        from hrma.engines.combustion_analysis import gamma_is_physical
        assert gamma_is_physical(deger) is beklenen

    def test_bool_sayi_sayilmaz(self):
        """Merkezî kuralın getirdiği tek sertleşme: ``bool`` sayı değildir."""
        from hrma.engines.combustion_analysis import gamma_is_physical
        assert gamma_is_physical(True) is False
        assert gamma_is_physical(False) is False
