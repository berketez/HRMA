"""ÖH D29 / termo-uçuş aşama-1 bekçisi — OH-D28-01.

Kalem: ``tests/test_field_wiring_layer_b.py::test_no_fabricated_constant_outputs``
listesinde kalan DOKUZ sabit yaprak (hepsi ``acoustic_modes`` bloğunda,
sahibi bu kulvar). Hüküm iki parçalıdır ve bu dosya ikisini de ölçer:

1. ÖNCE KUSUR: aynı bloğun eksiksizlik beyanı YALAN söyleyebiliyordu.
   ``_needed_caps`` enine (m, n) ihtiyaç aramasını güvenlik tavanında
   kesiyor, bu yüzden ihtiyaç tavanın üstündeyse dönen sayı tavana EŞİT
   oluyor ve ``m_need > m_cap`` kıyası False veriyordu; havuz eksik
   olduğu hâlde ``truncated=False`` + ``complete_below_hz=<sayı>``
   yayımlanıyordu (fail-closed ihlali). ÖLÇÜLDÜ:
   ``docs/scofield/raw/OH/D29/termo-ucus/a1/once_d2801.json`` (K6).
2. SONRA SINIFLANDIRMA: dokuz yaprağın her biri ya yayımlanan bir model
   eşiği/tohumu ya da kenetli bir özdeşliktir; künyeleri yanıtta ADIYLA
   durur ve ölçülen kardeşleri CANLI kalır. Bu dosya künyelerin varlığını
   ve imlerin DARLIĞINI mekanik olarak sınar — im listesi genişlerse ya da
   künye kaldırılırsa kırmızı verir.

Bu dosya ürün yolunu (``/calculate``) çağırmaz: hükmün tamamı analiz
sınıfının kendi yüzeyinde ölçülebilir ve makine paylaşımlı ortamda hızlı
koşması gerekir. Uçtan uca kanıt Katman B bekçisinin kendisidir.
"""
import ast
import os

import pytest

from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_BAND_MAX,
    CHUG_DP_RATIO_MINIMUM,
    AcousticModeAnalyzer,
    sound_speed,
    transverse_frequency,
    transverse_root,
)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Ölçüm noktası: hibrit taban yükünün çözülmüş kamara durumuna yakın gaz.
GAZ = dict(chamber_temperature=3000.0, gamma=1.2, gas_constant=350.0)

#: OH-D28-01'in dokuz yaprağı — Katman B'nin im listesinde ADIYLA duracak.
DOKUZ_YAPRAK_IMI = (
    'acoustic_modes.mode_pool.tangential_max_m',
    'acoustic_modes.mode_pool.radial_max_n',
    'acoustic_modes.mode_pool.seed_bounds.tangential_max_m',
    'acoustic_modes.mode_pool.seed_bounds.radial_max_n',
    'acoustic_modes.mode_pool.seed_bounds.longitudinal_max_q',
    'acoustic_modes.mode_pool.requested_n_modes',
    'acoustic_modes.mode_pool.returned_n_modes',
    'acoustic_modes.stability_report.chug.design_band_min_ratio',
    'acoustic_modes.stability_report.chug.design_band_max_ratio',
)


def _analiz(**override):
    an = AcousticModeAnalyzer()
    for k, v in override.items():
        setattr(an, k, v)
    return an


def _havuz(D, L, n_modes=10, **override):
    return _analiz(**override).analyze(
        chamber_diameter=D, chamber_length=L, n_modes=n_modes,
        **GAZ)['mode_pool']


def _kaynak(yol):
    with open(os.path.join(KOK, yol), encoding='utf-8') as f:
        return f.read()


def _katman_b_imleri():
    """Katman B'nin ``LEGITIMATE_CONSTANTS`` demetini AST'ten değerlendir."""
    src = _kaynak('tests/test_field_wiring_layer_b.py')
    agac = ast.parse(src)
    for d in agac.body:
        hedefler = (d.targets if isinstance(d, ast.Assign)
                    else [d.target] if isinstance(d, ast.AnnAssign) else [])
        if any(getattr(t, 'id', '') == 'LEGITIMATE_CONSTANTS'
               for t in hedefler):
            return eval(  # noqa: S307 — depo içi kaynak, AST'ten derlenmiş
                compile(ast.Expression(body=d.value), '<imler>', 'eval'))
    raise AssertionError('LEGITIMATE_CONSTANTS bulunamadi')


# ===========================================================================
# 1) FAIL-CLOSED: eksiksizlik beyani yalan soyleyemez
# ===========================================================================
class TestOHD2801EksiksizlikBeyani:
    """``mode_pool.truncated`` guvenlik tavani doyunca da dogruyu soyler."""

    #: Kusurun olculdugu kurgu (once_d2801.json K6): basik/genis kavite +
    #: DUSUK enine guvenlik tavani. Bogazlanan aile ENINE'dir; boyuna aile
    #: bol oldugu icin havuz talebi karsilar, yani "havuz yetmedi" dali
    #: DEVREYE GIRMEZ ve tek soru eksikligin BEYAN edilip edilmedigidir.
    DOYAN = dict(D=1.20, L=1.00, n_modes=10,
                 POOL_HARD_MAX_TANGENTIAL=2, POOL_HARD_MAX_RADIAL=1,
                 MAX_TANGENTIAL_INDEX=2, MAX_RADIAL_INDEX=1)

    def _doyan_havuz(self):
        d = dict(self.DOYAN)
        return _havuz(d.pop('D'), d.pop('L'), n_modes=d.pop('n_modes'), **d)

    def test_tavan_doyunca_gercek_mod_KACIYOR(self):
        """Once kusurun ONCULU olculur: kacan mod GERCEKTEN var mi?"""
        d = dict(self.DOYAN)
        D, L, nm = d.pop('D'), d.pop('L'), d.pop('n_modes')
        tam = _analiz(**d).analyze(chamber_diameter=D, chamber_length=L,
                                   n_modes=nm, **GAZ)
        hp = tam['mode_pool']
        f_cut = max(m['frequency_hz'] for m in tam['modes'])
        a = sound_speed(GAZ['gamma'], GAZ['gas_constant'],
                        GAZ['chamber_temperature'])
        kacan = [(m, n)
                 for m in range(0, 12) for n in range(0, 12)
                 if not (m == 0 and n == 0)
                 and transverse_frequency(a, D, transverse_root(m, n)) <= f_cut
                 and (m > hp['tangential_max_m'] or n > hp['radial_max_n'])]
        assert kacan, (
            'duzenek bozuk: bu kurguda kesim frekansinin altinda kacan '
            'enine mod YOK, dolayisiyla asagidaki beyan iddiasi anlamsiz')
        # Olculen (once_d2801.json K6): kacan tek mod 3T, 1250,91 Hz;
        # kesim frekansi 1444,65 Hz.
        assert (3, 0) in kacan

    def test_kacan_mod_varken_TRUNCATED_beyan_edilir(self):
        """KUSUR: tabanda burada ``truncated=False`` yayimlaniyordu."""
        hp = self._doyan_havuz()
        assert hp['truncated'] is True, (
            'guvenlik tavani baglamis ve kesim frekansinin altinda gercek '
            'mod dusmus, buna ragmen havuz EKSIKSIZ beyan ediliyor')

    def test_eksik_havuzda_complete_below_hz_SAYI_YAYIMLAMAZ(self):
        """Fail-closed: hukum kazanilmadiysa sayi yayimlanmaz."""
        hp = self._doyan_havuz()
        assert hp['complete_below_hz'] is None, (
            'eksik havuz icin "su frekansin altinda eksiksiz" sayisi '
            'yayimlanmis: %r' % (hp['complete_below_hz'],))
        assert 'TRUNCATED' in hp['basis']

    def test_needed_caps_DOYMAYI_ADIYLA_dondurur(self):
        """Tek kaynak: doyma bilgisi cagirana ayri bir deger olarak gider."""
        an = _analiz(POOL_HARD_MAX_TANGENTIAL=2, POOL_HARD_MAX_RADIAL=1)
        a = sound_speed(GAZ['gamma'], GAZ['gas_constant'],
                        GAZ['chamber_temperature'])
        sonuc = an._needed_caps(a, 1.20, 1.00, 1444.65)
        assert len(sonuc) == 4, (
            '_needed_caps doyma bayragini dondurmuyor: %r' % (sonuc,))
        assert sonuc[3] is True
        # Ayni tavanlar bol oldugunda doyma YOKTUR (bayrak her zaman True
        # donen bir tautoloji degildir).
        gevsek = _analiz()._needed_caps(a, 1.20, 1.00, 1444.65)
        assert gevsek[3] is False

    def test_bol_tavanda_eksiksizlik_beyani_KORUNUR(self):
        """Onarim, dogru olan beyani bozmaz (asiri-fail-closed degil)."""
        hp = _havuz(0.15, 1.0)
        assert hp['truncated'] is False
        assert isinstance(hp['complete_below_hz'], float)
        assert hp['complete_below_hz'] > 0.0


# ===========================================================================
# 2) DOKUZ YAPRAGIN SINIFLANDIRMASI — kunye + olculen kardes
# ===========================================================================
class TestOHD2801HavuzTavanlari:
    """1-2: ``tangential_max_m`` / ``radial_max_n`` basamak fonksiyonudur."""

    def test_tavan_tohumun_ALTINA_inmez_ve_kaynagini_beyan_eder(self):
        hp = _havuz(0.15, 1.0)
        tohum = hp['seed_bounds']
        assert hp['tangential_max_m'] >= tohum['tangential_max_m']
        assert hp['radial_max_n'] >= tohum['radial_max_n']
        assert hp['cap_source']['tangential_max_m'] == 'seed_floor'
        assert hp['cap_source']['radial_max_n'] == 'seed_floor'
        assert 'seed_floor' in hp['cap_basis']

    @pytest.mark.parametrize('D,L,nm,alan,beklenen', [
        # ÖLÇÜLDÜ (once_d2801.json K1) — bant geçişi:
        (0.15, 1.00, 10, 'tangential_max_m', 3),    # tohum tabani
        (1.20, 0.10, 10, 'tangential_max_m', 8),    # tohumun ustune buyudu
        (1.20, 0.10, 40, 'radial_max_n', 17),       # radyal tavan kalkti
        (0.60, 0.30, 60, 'radial_max_n', 4),
    ])
    def test_tavan_kavite_oraniyla_BASAMAK_yapiyor(self, D, L, nm, alan,
                                                   beklenen):
        """Sabit YAZILMIS sayi degil: bant gecisi olculur."""
        hp = _havuz(D, L, n_modes=nm)
        assert hp[alan] == beklenen
        tohum = hp['seed_bounds'][alan]
        assert (hp['cap_source'][alan] == 'grown_beyond_seed') == (
            hp[alan] > tohum)

    def test_tavanin_CANLI_kardesleri_sabit_listesinde_degil(self):
        """Ime alinan iki tavanin kardesleri olculmeye devam ediyor."""
        imler = _katman_b_imleri()
        for canli in ('mode_pool.longitudinal_max_q',
                      'mode_pool.candidate_count'):
            assert not any(im in '.motor.acoustic_modes.' + canli
                           for im in imler), (
                '%s imlenmis — havuzun canli kardesi ortulemez' % canli)


class TestOHD2801TohumSinirlari:
    """3-5: ``seed_bounds.*`` sinif ozniteliklerinin TEK KAYNAGIDIR."""

    def test_tohum_yapraklari_sinif_sabitlerini_izler(self):
        hp = _havuz(0.15, 1.0)
        assert hp['seed_bounds'] == {
            'tangential_max_m': AcousticModeAnalyzer.MAX_TANGENTIAL_INDEX,
            'radial_max_n': AcousticModeAnalyzer.MAX_RADIAL_INDEX,
            'longitudinal_max_q': AcousticModeAnalyzer.MAX_LONGITUDINAL_INDEX,
        }

    def test_tohum_degisince_yapraklar_BIREBIR_izler(self):
        """Yanita sabit yazilmis sayi olsaydi bu test kirmizi olurdu."""
        hp = _havuz(0.15, 1.0, MAX_TANGENTIAL_INDEX=5, MAX_RADIAL_INDEX=4,
                    MAX_LONGITUDINAL_INDEX=9)
        assert hp['seed_bounds'] == {'tangential_max_m': 5, 'radial_max_n': 4,
                                     'longitudinal_max_q': 9}

    def test_tohum_kunyesi_yapragin_yaninda_duruyor(self):
        hp = _havuz(0.15, 1.0)
        assert 'MAX_TANGENTIAL_INDEX' in hp['seed_bounds_basis']
        assert 'floor' in hp['seed_bounds_basis']


class TestOHD2801ModSayaclari:
    """6-7: ``requested_n_modes`` cagiranin izgarasi, ``returned`` kenetli."""

    @pytest.mark.parametrize('nm', [5, 10, 25])
    def test_requested_cagirani_BIREBIR_izler(self, nm):
        assert _havuz(0.15, 1.0, n_modes=nm)['requested_n_modes'] == nm

    def test_returned_min_ozdesligi_HER_KOSUMDA_tutuyor(self):
        hp = _havuz(0.15, 1.0)
        assert hp['returned_n_modes'] == min(hp['requested_n_modes'],
                                             hp['candidate_count'])

    def test_KENET_acilinca_iki_sayac_ayrisiyor(self):
        """Olculdu (K2): havuz 3 adaya inince requested 10, returned 3."""
        hp = _havuz(0.15, 1.0, n_modes=10,
                    MAX_TANGENTIAL_INDEX=0, MAX_RADIAL_INDEX=0,
                    MAX_LONGITUDINAL_INDEX=3, POOL_HARD_MAX_TANGENTIAL=0,
                    POOL_HARD_MAX_RADIAL=0, POOL_HARD_MAX_LONGITUDINAL=3)
        assert hp['requested_n_modes'] == 10
        assert hp['returned_n_modes'] == 3
        assert hp['candidate_count'] == 3
        # Kenet acildiginda eksiklik SESSIZ kalmaz.
        assert hp['truncated'] is True

    def test_sayac_kunyesi_yapragin_yaninda_duruyor(self):
        hp = _havuz(0.15, 1.0)
        assert 'caller grid size' in hp['mode_count_basis']
        assert 'min(requested, candidate_count)' in hp['mode_count_basis']


class TestOHD2801ChugTasarimBandi:
    """8-9: bandin iki ucu YAYIMLANAN esiktir, hukum kardeslerde verilir."""

    def test_band_uclari_TEK_KAYNAKTAN_geliyor(self):
        c = _analiz().analyze(chamber_diameter=0.15, chamber_length=1.0,
                              injector_dp_ratio=0.2,
                              **GAZ)['stability_report']['chug']
        assert c['design_band_min_ratio'] == CHUG_DP_RATIO_MINIMUM
        assert c['design_band_max_ratio'] == CHUG_DP_RATIO_BAND_MAX
        # Alt uc, ayni sozlukteki hard_min_ratio ile AYNI beyanli sayidir:
        # ikinci bir sayi uretilmiyor (TEK KAYNAK).
        assert c['design_band_min_ratio'] == c['hard_min_ratio']
        assert 'threshold' in c['design_band_basis']

    @pytest.mark.parametrize('oran,beklenen_durum', [
        (0.05, 'AT_RISK'), (0.15, 'MARGINAL'), (0.20, 'OK'), (0.40, 'OK'),
    ])
    def test_hukum_veren_KARDESLER_canli(self, oran, beklenen_durum):
        """Olculdu (K5): band sabitken hukum girdiyle degisiyor."""
        c = _analiz().analyze(chamber_diameter=0.15, chamber_length=1.0,
                              injector_dp_ratio=oran,
                              **GAZ)['stability_report']['chug']
        assert c['status'] == beklenen_durum
        assert c['injector_dp_ratio'] == pytest.approx(oran)
        if oran > CHUG_DP_RATIO_BAND_MAX:
            assert c['above_design_band'] is True
            assert c['design_band_excess_factor'] == pytest.approx(
                oran / CHUG_DP_RATIO_BAND_MAX)


# ===========================================================================
# 3) IM DISIPLINI — dokuz im ADIYLA var, DAR ve esik iki yanli 0
# ===========================================================================
class TestOHD2801ImDisiplini:

    def test_dokuz_im_katman_B_listesinde_ADIYLA_duruyor(self):
        imler = _katman_b_imleri()
        eksik = [im for im in DOKUZ_YAPRAK_IMI if im not in imler]
        assert not eksik, 'im listesinden dusen yaprak: %s' % eksik

    @pytest.mark.parametrize('im', DOKUZ_YAPRAK_IMI)
    def test_her_im_TEK_yapragi_kapsiyor(self, im):
        """Genis im (blok adi) sonradan dogacak uydurmayi da orter."""
        dokuz_yol = ['.motor.acoustic_modes.' + y for y in (
            'mode_pool.tangential_max_m', 'mode_pool.radial_max_n',
            'mode_pool.seed_bounds.tangential_max_m',
            'mode_pool.seed_bounds.radial_max_n',
            'mode_pool.seed_bounds.longitudinal_max_q',
            'mode_pool.requested_n_modes', 'mode_pool.returned_n_modes',
            'stability_report.chug.design_band_min_ratio',
            'stability_report.chug.design_band_max_ratio')]
        eslesen = [y for y in dokuz_yol if im in y]
        assert len(eslesen) == 1, (
            '%r imi %d yapraga birden uyuyor: %s' % (im, len(eslesen),
                                                     eslesen))
        # Ayni im, bu bloktaki CANLI kardeslere DE uymamali.
        canli = ['.motor.acoustic_modes.' + y for y in (
            'mode_pool.longitudinal_max_q', 'mode_pool.candidate_count',
            'mode_pool.complete_below_hz',
            'stability_report.chug.injector_dp_ratio',
            'stability_report.chug.design_band_excess_factor')]
        assert not [y for y in canli if im in y], (
            '%r imi canli bir kardesi de yutuyor' % (im,))

    def test_esik_IKI_YANLI_ve_sifirda(self):
        """Borc odendi: esigin iki yani da olculen 0'dir."""
        src = _kaynak('tests/test_field_wiring_layer_b.py')
        import re
        ust = re.search(r'assert len\(suspicious\) <= (\d+)', src)
        alt = re.search(r'assert len\(suspicious\) >= (\d+)', src)
        assert ust and alt, 'esigin bir yani kaldirilmis'
        assert int(ust.group(1)) == 0 and int(alt.group(1)) == 0, (
            'esik 0/0 degil: <=%s / >=%s' % (ust.group(1), alt.group(1)))
