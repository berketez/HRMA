"""ÖH D28 · sivi a1 — OH-D26-09 (kalan yarı) + OH-D27-02 bekçileri.

Kalem
-----
Pompa kartı KADEME SAYISINI hiç yayımlamıyordu ve çarkı TOPLAM yükle tek
kademe çözüyordu. Aynı yanıttaki ``turbopump_sizing`` bloğu ise aynı pompa
için 2/3/4/6 kademe yayımlıyordu: tek pompa, iki blok, iki karar. Bu,
türbin tarafında P3B4-02 / Z5S-PK1'in kapattığı kusurun pompa ikizidir
(``tests/test_sivi_baglama_beyan.py::test_turbin_kademe_sayisi_iki_blokta_ayni``
"Kademe sayısı bir TASARIM KARARIDIR; iki blok iki karar veremez").

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D28/sivi/a1/{once,sonra}.json``; beş motor,
on pompa kartı):

  * kademe alanı yayımlayan kart              0 -> 10
  * radyal bandın ALTINDA olup kademesi
    yayımlanmayan pompa                       5 -> 0
  * iki blok kademe çelişkisi                 4 -> 0
  * iki çap kestiriminin ORANI (kart Euler
    çapı / modül baş-katsayısı çapı) bandı
                       [0,477 - 1,124] -> [1,062 - 1,147]  (yayılım 0,647 -> 0,084)
  * aynı oran x sqrt(n) bandı
                       [1,062 - 1,169] -> [1,062 - 2,809]

İkinci satır kusurun sayısal parmak iziydi: kart ``impeller_diameter_ratio``
alanını "tasarım olgunluğu göstergesi" diye yayımlıyordu, ama oran modelin
değil KADEME SAYISININ ölçüsüydü (1,12/sqrt(n): n=1'de 1,06-1,12; n=2'de
0,810; n=3'te 0,671; n=4'te 0,582; n=6'da 0,477). Onarımdan sonra oran
kademe sayısından bağımsızdır — çünkü iki model artık AYNI çarkı tahmin
ediyor.

Bekçiler SAYI ÇAPASI DEĞİL İLİŞKİ bekçisidir: kart hangi devri/debiyi/yükü
yayımlarsa yayımlasın, kademe kararı o üçlüden ve modülün TEK kuralından
çıkmak zorundadır ve çark o kararın KADEME yükünü kaldırmak zorundadır.
"""
import math

import pytest

pytestmark = pytest.mark.usefixtures()


def _motor(**kw):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    eng = LiquidRocketEngine(**kw)
    return eng.calculate_performance()


@pytest.fixture(scope='module')
def sonuc_25kn():
    return _motor(thrust=25000, chamber_pressure=60, mixture_ratio=2.3,
                  fuel_type='rp1', oxidizer_type='lox')


@pytest.fixture(scope='module')
def besleme_25kn(sonuc_25kn):
    return sonuc_25kn['detailed_feed_system']


@pytest.fixture(scope='module')
def sonuc_500kn_ffsc():
    """Ns = 103 US: kademe TAVANINDA bile radyal bandın altında kalan vaka."""
    return _motor(thrust=500000, chamber_pressure=250, mixture_ratio=3.4,
                  fuel_type='methane', oxidizer_type='lox',
                  overrides={'engine_cycle': 'full_flow_staged'})


PUMPALAR = ('oxidizer_pump', 'fuel_pump')


class TestOHD2702KademeKarariYayimlanir:
    """Mutasyon hedefleri: (1) kademe alanları yine yok, (2) karar kuraldan
    kopuk, (3) çark yine TOPLAM yükle çözülüyor."""

    @pytest.mark.parametrize('ad', PUMPALAR)
    def test_kademe_alanlari_YAPISAL_olarak_var(self, besleme_25kn, ad):
        p = besleme_25kn['turbopump_analysis'][ad]
        n = p['stage_count']
        assert isinstance(n, int) and not isinstance(n, bool) and n >= 1, (
            f'{ad}: kademe sayısı yapısal bir alan değil: {n!r}')
        assert isinstance(p['stage_head_m'], float) and p['stage_head_m'] > 0
        assert isinstance(p['specific_speed_per_stage_us'], float)
        assert p['stage_count_status'] in (
            'in_centrifugal_band', 'below_band_at_stage_cap',
            'above_centrifugal_band')
        assert str(p['stage_count_basis']).strip()
        assert str(p['stage_count_status_basis']).strip()

    @pytest.mark.parametrize('ad', PUMPALAR)
    def test_karar_MODULUN_KURALINDAN_turetilir(self, besleme_25kn, ad):
        """Kart ikinci bir kademe kuralı yazmaz; kuralı modülden okur."""
        from hrma.analysis.turbopump_sizing import (
            NS_CENTRIFUGAL_MIN_US, PUMP_STAGES_MAX, pump_stage_count)

        p = besleme_25kn['turbopump_analysis'][ad]
        ns = float(p['specific_speed_us'])
        n = int(p['stage_count'])
        assert n == pump_stage_count(ns), (
            f'{ad}: Ns = {ns:.1f} US için kural {pump_stage_count(ns)} kademe '
            f'diyor, kart {n} yayımlıyor')
        assert n <= PUMP_STAGES_MAX
        # Kademe başına özgül devir kartın KENDİ Ns'inden çıkar.
        assert float(p['specific_speed_per_stage_us']) == pytest.approx(
            ns * n ** 0.75, rel=1e-12)
        # Kademe yükü kartın KENDİ toplam yükünden çıkar.
        assert float(p['stage_head_m']) == pytest.approx(
            float(p['design_head']) / n, rel=1e-12)
        # Sınıf, kademe başına Ns'ten türetilir (sayı çapası değil).
        beklenen = ('below_band_at_stage_cap'
                    if float(p['specific_speed_per_stage_us'])
                    < NS_CENTRIFUGAL_MIN_US else 'in_centrifugal_band')
        if p['stage_count_status'] != 'above_centrifugal_band':
            assert p['stage_count_status'] == beklenen

    @pytest.mark.parametrize('ad', PUMPALAR)
    def test_iki_blok_TEK_karar(self, besleme_25kn, ad):
        """Aynı pompa için boyutlandırma bloğu ve kart aynı sayıyı der."""
        kart = besleme_25kn['turbopump_analysis'][ad]
        blok = besleme_25kn['turbopump_sizing'].get(ad) or {}
        modul = (blok.get('pump') or {}) if blok.get('status') == 'modelled' \
            else {}
        if not modul:
            pytest.skip('turbopump_sizing bu pompayı boyutlandırmadı')
        assert int(kart['stage_count']) == int(modul['stage_count']), (
            f"{ad}: kart {kart['stage_count']} kademe, boyutlandırma "
            f"{modul['stage_count']} kademe — tek pompa, iki karar")

    @pytest.mark.parametrize('ad', PUMPALAR)
    def test_cark_KADEME_yukunu_kaldirir_toplam_yuku_DEGIL(
            self, besleme_25kn, ad):
        """Yayımlanan çark, kartın KENDİ Euler bağıntısında kademe yükünü verir.

        Bu bekçi kusurun tam kalbindedir: çark toplam yükle çözülürse
        yayımlanan uç hızı ``stage_head_m``i DEĞİL ``design_head``i üretir.
        """
        from hrma.engines.liquid_rocket_engine import (
            PUMP_BLADE_COUNT, PUMP_BLADE_EXIT_ANGLE_DEG,
            PUMP_EXIT_WIDTH_RATIO, PUMP_HYDRAULIC_EFFICIENCY)

        p = besleme_25kn['turbopump_analysis'][ad]
        if p.get('impeller_geometry_status') != 'modelled':
            pytest.skip('çark geometrisi bu koşumda yayımlanmıyor')
        g0 = 9.80665
        u2 = float(p['impeller_tip_speed'])
        d2 = float(p['impeller_diameter'])
        q = float(p['volumetric_flow_m3_s'])
        beta2 = math.radians(PUMP_BLADE_EXIT_ANGLE_DEG)
        slip = 1.0 - math.pi * math.sin(beta2) / PUMP_BLADE_COUNT
        a2 = math.pi * d2 ** 2 * PUMP_EXIT_WIDTH_RATIO
        h_kademe = PUMP_HYDRAULIC_EFFICIENCY * (
            slip * u2 ** 2 - u2 * q / (a2 * math.tan(beta2))) / g0
        assert h_kademe == pytest.approx(float(p['stage_head_m']), rel=1e-6), (
            f'{ad}: yayımlanan çark {h_kademe:.2f} m kaldırıyor, kartın '
            f"kademe yükü {p['stage_head_m']:.2f} m — çark kademe kararıyla "
            'çözülmemiş')
        n = int(p['stage_count'])
        if n > 1:
            assert h_kademe != pytest.approx(float(p['design_head']),
                                             rel=1e-3), (
                f'{ad}: {n} kademeli pompada çark hâlâ TOPLAM yükü '
                f"({p['design_head']:.2f} m) tek başına kaldırıyor")

    @pytest.mark.parametrize('ad', PUMPALAR)
    def test_HQ_egrisi_POMPANIN_egrisidir_tek_kademenin_DEGIL(
            self, besleme_25kn, ad):
        """Yayımlanan H-Q eğrisi tasarım debisinde pompanın yükünü vermeli.

        Euler yükü debide DOĞRUSAL olduğu için eğrinin iki ucu onu tam
        belirler; tasarım debisindeki değer ``design_head`` olmak
        zorundadır. Eğri kademe çarpanını kaybederse (tek kademenin
        eğrisi yayımlanırsa) bu değer ``design_head/stage_count``a düşer
        ve kart kendi içinde çelişir.
        """
        p = besleme_25kn['turbopump_analysis'][ad]
        q_list = list(p['flow_range'])
        h_list = list(p['head_curve'])
        assert len(q_list) == len(h_list) >= 2
        q0, q1 = float(q_list[0]), float(q_list[-1])
        h0, h1 = float(h_list[0]), float(h_list[-1])
        mdot = float(p['design_flow_rate'])
        h_tasarim = h0 + (h1 - h0) * (mdot - q0) / (q1 - q0)
        assert h_tasarim == pytest.approx(float(p['design_head']),
                                          rel=1e-5), (
            f'{ad}: H-Q eğrisi tasarım debisinde {h_tasarim:.2f} m veriyor, '
            f"kartın basma yüksekliği {p['design_head']:.2f} m "
            f"({p['stage_count']} kademe) — eğri pompanın değil tek "
            'kademenin eğrisi')

    def test_cap_orani_kademe_sayisindan_BAGIMSIZ(self, besleme_25kn):
        """İki bağımsız çap kestiriminin oranı model farkını ölçmeli, sqrt(n)'i değil.

        ÖLÇÜLDÜ (once.json): 25 kN koşumunda oks (2 kademe) 0,810 ⟷ yakıt
        (1 kademe) 1,062 — %24 ayrık. Onarımdan sonra 1,105 ⟷ 1,062 (%4).
        """
        oranlar = {}
        for ad in PUMPALAR:
            blok = besleme_25kn['turbopump_sizing'].get(ad) or {}
            oran = blok.get('impeller_diameter_ratio')
            n = ((blok.get('pump') or {}).get('stage_count')
                 if blok.get('status') == 'modelled' else None)
            if isinstance(oran, float) and isinstance(n, int):
                oranlar[ad] = (oran, n)
        assert len(oranlar) == 2, f'iki pompa da ölçülemedi: {oranlar}'
        assert len({n for _o, n in oranlar.values()}) == 2, (
            'bu koşum tek ve çok kademeli pompayı bir arada içermiyor; '
            f'bekçi anlamını yitirir: {oranlar}')
        (o1, n1), (o2, n2) = oranlar.values()
        ayrisma = abs(o1 - o2) / max(abs(o1), abs(o2))
        assert ayrisma < 0.15, (
            f'iki çap kestiriminin oranı kademe sayısıyla değişiyor: '
            f'{n1} kademede {o1:.3f}, {n2} kademede {o2:.3f} '
            f'(%{ayrisma * 100:.1f} ayrık). Oran model farkını değil '
            'sqrt(kademe) çarpanını ölçüyor demektir.')


class TestOHD2702KademeTavaniBeyani:
    """Kademe TAVANINDA bile radyal bandın altında kalan tasarım ADIYLA
    'geçerlilik dışı' der; sessizce tek kademe gibi yayımlanmaz."""

    def test_tavanda_bile_bant_alti_kalan_tasarim_adiyla_beyan_edilir(
            self, sonuc_500kn_ffsc):
        from hrma.analysis.turbopump_sizing import (
            NS_CENTRIFUGAL_MIN_US, PUMP_STAGES_MAX)

        p = (sonuc_500kn_ffsc['detailed_feed_system']['turbopump_analysis']
             ['oxidizer_pump'])
        assert int(p['stage_count']) == PUMP_STAGES_MAX, (
            'bu vaka kademe tavanını zorlamıyor; bekçi anlamını yitirir')
        assert float(p['specific_speed_per_stage_us']) < NS_CENTRIFUGAL_MIN_US
        assert p['stage_count_status'] == 'below_band_at_stage_cap', (
            f"tavanda bile bant altı kalan tasarım {p['stage_count_status']!r} "
            'diye yayımlanıyor')
        kunye = str(p['stage_count_status_basis'])
        assert 'validity' in kunye.lower(), (
            'geçerlilik dışı hükmü künyede söylenmiyor: ' + kunye)
