"""SÜRTÜNME İTKİ KAYBI GÖÇ MANİFESTOSU — 16 Ağustos 2026.

NE OLDU
-------
Yarı-1B lüle katmanı (``hrma.analysis.nozzle_flow_1d.NozzleFlow1D``) itki
kaybını yıllardır tek bir defter sabitinden alıyordu: %1,5
(``hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT``). V5 partisinde
(``hrma/flow/boundary_layer.py``) aynı lüle için GERÇEK bir sıkıştırılabilir
momentum-integral sınır tabakası çözümü depoya girdi ve sayı ÖLÇÜLÜR oldu;
o parti bilinçli olarak varsayılanı değiştirmedi, iki sayıyı yan yana
yayımladı.

Berke kararı (16 Ağu 2026): **"doğrusu neyse o olsun"** — uydurma sabit
varsayılan olmaktan çıkar, ÖLÇÜLEN değer varsayılan olur.

Politika (``docs/mimari/f2-yanma-tepkisi-tasarimi.md`` §8.1, karar 8):
"değişiklik serbest" DEĞİL, **"açıklanmış değişiklik serbest"**. Bu dosya
o açıklamanın kendisidir: her yayımlanan sayı için
``eski_varsayılan → yeni_ölçülen → Δmutlak → Δbağıl → gerekçe`` kaydı
üretilir ve DOĞRULANIR. Beklenmeyen fark → test KIRMIZI.

MANİFESTONUN İDDİA ETTİĞİ ŞEY
-----------------------------
1. Yeni sayı 9 vakanın hepsinde ÖLÇÜMDEN gelir ve Sutton & Biblarz'ın
   (9. baskı, Böl. 3.5) %0,5-2 bandındadır.
2. Fark HER ZAMAN "kazanç" değildir: ölçülen kayıp boğaz Reynolds sayısına
   kuvvetle bağlıdır. Büyük lülelerde eski sabit KÖTÜMSER (%1,5 > ölçülen),
   ~12 mm'nin altındaki boğazlarda İYİMSERDİR (%1,5 < ölçülen). Yani göç
   bazı motorlarda itkiyi DÜŞÜRÜR — bu, sabitin gizlediği gerçek fizik.
3. Değişimin yarıçapı ÖLÇÜLDÜ: yarı-1B çıktısında yalnız 5 yaprak oynar
   (1392 yapraktan), üç motor ucunda (``/calculate``,
   ``/calculate_solid``, ``/calculate_liquid``) SIFIR yaprak oynar —
   çünkü o zincirler bu çözücüyü hiç çağırmıyor (ölçüldü, bekçili).
4. Eski davranışa dönüş yolu açıktır ve bit-özdeştir:
   ``friction_loss_fraction=0.015`` geçmek.

MODEL BELİRSİZLİĞİ (yeni varsayılanın künyesi)
----------------------------------------------
Ölçüm, V5'in doğrulama merdiveninde şu bantlarla sınandı
(``tests/flow/test_sinir_tabakasi.py``): laminer düz levhada Blasius'a
karşı c_f +%0,90 / θ +%1,01 / δ* +%1,75 / H +%0,78; türbülanslı düz
levhada Schultz-Grunow'a (NACA TM 986) karşı c_f −%2,6…−%3,9
(Ludwieg-Tillmann kapanışının bilinen sistematik yönü). Yeni varsayılan
bu model belirsizliğini ve ``boundary_layer.not_modelled`` listesindeki
her şeyi (özellikle cidar pürüzlülüğü — gerçek sürtünmeyi ARTIRIR — ve
yeniden laminerleşme — DÜŞÜRÜR) taşır. Sabitin "%1,5" belirsizliği ise
hiçbir zaman ölçülmemişti.
"""

import json
import math

import pytest

from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
from hrma.constants import NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT as ESKI_SABIT
from tests.support import shake

#: Göç öncesi varsayılan — manifesto boyunca "eski" sütunu budur.
#: (Sabitin KENDİSİ değişmedi; yalnız rolü "varsayılan"dan "yedek"e indi.)
ESKI_VARSAYILAN = 0.015

#: Sutton & Biblarz 9. baskı Böl. 3.5 sürtünme/sınır tabakası kaybı bandı.
SUTTON_BANDI = (0.005, 0.020)

#: Altın değerlerin bandı. Sayısal gürültü payı DEĞİL model kayması
#: ölçüsüdür: kapanış/marş/geometri değişirse ölçülen kesir bu bandı aşar
#: ve manifesto kırmızıya döner (V5'in kendi regresyon bandıyla aynı: %3).
ALTIN_BANT = 0.03


# ===========================================================================
# MANİFESTO TABLOSU — 9 vaka
# ===========================================================================
# Sütunlar: eski_varsayılan(0,015) → yeni_ölçülen → Δmutlak → Δbağıl → gerekçe
# 'olculen' değerleri 16 Ağu 2026'da ÖLÇÜLDÜ (bu depo, bu kapanışlar).
MANIFESTO = (
    dict(
        ad='vakum_70bar_eps25',
        vaka=dict(chamber_pressure=70e5, chamber_temperature=3500.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.10,
                  expansion_ratio=25.0, ambient_pressure=0.0),
        rejim='underexpanded', kaynak='integral_bl_measured',
        olculen=0.013801691,
        gerekce=('BL ölçümü (D_t = 100 mm, tam akış): Sutton bandı içinde; '
                 'yüksek boğaz Reynolds sayısı c_f\'yi düşürür, sabit '
                 'KÖTÜMSER kalıyordu'),
    ),
    dict(
        ad='deniz_70bar_eps25',
        vaka=dict(chamber_pressure=70e5, chamber_temperature=3500.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.10,
                  expansion_ratio=25.0, ambient_pressure=101325.0),
        rejim='separated', kaynak='integral_bl_measured',
        olculen=0.012827015,
        gerekce=('BL ölçümü, ayrılmış rejim: marş Summerfield ayrılma '
                 'düzleminde durur ve momentum itkisi de aynı düzleme '
                 'aittir — kesir aynı yüzeyin oranıdır'),
    ),
    dict(
        ad='orta_25bar_eps6',
        vaka=dict(chamber_pressure=25e5, chamber_temperature=3000.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.035,
                  expansion_ratio=6.0, ambient_pressure=50000.0),
        rejim='underexpanded', kaynak='integral_bl_measured',
        olculen=0.012319323,
        gerekce=('BL ölçümü (D_t = 35 mm, ε = 6): kısa ıslak yüzey, '
                 'Sutton bandının orta altı'),
    ),
    dict(
        ad='kucuk_20bar_eps4',
        vaka=dict(chamber_pressure=20e5, chamber_temperature=3000.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.02,
                  expansion_ratio=4.0, ambient_pressure=101325.0),
        rejim='overexpanded', kaynak='integral_bl_measured',
        olculen=0.011765445,
        gerekce=('BL ölçümü (aşırı genişlemiş ama ayrılmamış): tam akış '
                 'çıkışa kadar, kesir çıkış düzlemine ait'),
    ),
    dict(
        ad='buyuk_100bar_eps50',
        vaka=dict(chamber_pressure=100e5, chamber_temperature=3600.0,
                  gamma=1.15, molecular_weight=22.0, throat_diameter=0.25,
                  expansion_ratio=50.0, ambient_pressure=0.0),
        rejim='underexpanded', kaynak='integral_bl_measured',
        olculen=0.013351239,
        gerekce=('BL ölçümü (D_t = 250 mm, ε = 50): büyük ıslak yüzey '
                 'düşük c_f\'yi kısmen geri alır — kesir yine sabitin '
                 'altında'),
    ),
    dict(
        ad='kati_40bar_eps16',
        vaka=dict(chamber_pressure=40e5, chamber_temperature=3000.0,
                  gamma=1.2, molecular_weight=26.0, throat_diameter=0.05,
                  expansion_ratio=16.0, ambient_pressure=101325.0),
        rejim='separated', kaynak='integral_bl_measured',
        olculen=0.013444960,
        gerekce=('BL ölçümü, katı motor mertebesi (ε = 16 deniz '
                 'seviyesinde ayrılıyor): kesir ayrılma düzlemine ait'),
    ),
    dict(
        ad='mikro_60bar_eps10',
        vaka=dict(chamber_pressure=60e5, chamber_temperature=3200.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.010,
                  expansion_ratio=10.0, ambient_pressure=0.0),
        rejim='underexpanded', kaynak='integral_bl_measured',
        olculen=0.015581327,
        gerekce=('BL ölçümü, KARŞI ÖRNEK: D_t = 10 mm boğazda Re_θ ≈ 630, '
                 'c_f ~ Re^(−0,268) yükselir ve ölçülen kayıp %1,5 '
                 'SABİTİNİ AŞAR — eski sabit küçük motorlarda İYİMSERDİ '
                 '(itki bu vakada göçle DÜŞER)'),
    ),
    dict(
        ad='sogukgaz_10bar_eps4',
        vaka=dict(chamber_pressure=10e5, chamber_temperature=2800.0,
                  gamma=1.25, molecular_weight=28.0, throat_diameter=0.03,
                  expansion_ratio=4.0, ambient_pressure=101325.0),
        rejim='separated', kaynak='integral_bl_measured',
        olculen=0.011947726,
        gerekce=('BL ölçümü, düşük basınç + ağır gaz (γ = 1,25, '
                 'MW = 28): bandın alt ucuna yakın'),
    ),
    dict(
        ad='sok_6bar_eps25',
        vaka=dict(chamber_pressure=6e5, chamber_temperature=3000.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.05,
                  expansion_ratio=25.0, ambient_pressure=101325.0),
        rejim='normal_shock_in_nozzle', kaynak='legacy_constant',
        olculen=None,
        gerekce=('ÖLÇÜM YOK: lüle içi normal şok. Marş şokta durur, '
                 'momentum itkisi şok ARDI ses-altı çıkıştan gelir — iki '
                 'sayı aynı yüzeye ait olmadığı için kesir YAYIMLANMAZ '
                 '(V5 saha bulgusu 2). Yedek sabit kullanılır ve beyan '
                 'edilir'),
    ),
)

#: Gerekçe sınıfları: manifestonun izin verdiği TEK iki sınıf. Bir satır
#: bunların dışına düşerse (ör. "sebebi bilinmiyor") göç açıklanmamış
#: demektir ve test kırmızıdır.
BEKLENEN_SINIFLAR = ('BL ölçümü', 'ÖLÇÜM YOK')


def _cozum(vaka):
    return NozzleFlow1D(**vaka).solve()


def _satir(kayit, cozum):
    """Manifesto satırını ÖLÇÜMDEN kurar (elle yazılmış sayı yok)."""
    kayiplar = cozum['losses']
    yeni = kayiplar['friction_loss_fraction']
    olculen = kayiplar['friction_loss_fraction_integral_bl']
    d_mutlak = None if olculen is None else olculen - ESKI_VARSAYILAN
    return {
        'ad': kayit['ad'],
        'rejim': cozum['regime']['type'],
        'eski': ESKI_VARSAYILAN,
        'yeni': yeni,
        'kaynak': kayiplar['friction_loss_fraction_source'],
        'olculen': olculen,
        'delta_mutlak': d_mutlak,
        'delta_bagil': (None if d_mutlak is None
                        else d_mutlak / ESKI_VARSAYILAN),
        'itki_eski_N': kayiplar['thrust_effective_legacy_constant_N'],
        'itki_yeni_N': kayiplar['thrust_effective_N'],
        'gerekce': kayit['gerekce'],
    }


@pytest.fixture(scope='module')
def tablo():
    """9 vakanın manifesto tablosu (bir kez çözülür, testler paylaşır)."""
    return [_satir(k, _cozum(k['vaka'])) for k in MANIFESTO]


def _tablo_metni(tablo):
    basliklar = (f"{'vaka':22s} {'rejim':22s} {'eski':>7s} {'yeni':>10s} "
                 f"{'Δmutlak':>10s} {'Δbağıl':>9s} {'ΔF_itki':>9s}  kaynak")
    satirlar = [basliklar]
    for s in tablo:
        d_itki = (100.0 * (s['itki_yeni_N'] - s['itki_eski_N'])
                  / abs(s['itki_eski_N']))
        if s['olculen'] is None:
            satirlar.append(
                f"{s['ad']:22s} {s['rejim']:22s} {s['eski']:7.4f} "
                f"{s['yeni']:10.6f} {'—':>10s} {'—':>9s} "
                f"{d_itki:8.4f}%  {s['kaynak']}")
        else:
            satirlar.append(
                f"{s['ad']:22s} {s['rejim']:22s} {s['eski']:7.4f} "
                f"{s['yeni']:10.6f} {s['delta_mutlak']:+10.6f} "
                f"{100 * s['delta_bagil']:+8.3f}% {d_itki:8.4f}%  "
                f"{s['kaynak']}")
    return '\n'.join(satirlar)


# ===========================================================================
# (1) MANİFESTO: her satır doğrulanır
# ===========================================================================
class TestManifesto:
    def test_tablo_yazdirilir_ve_tam(self, tablo):
        """9 satır; tablo metni ``pytest -s`` ile insan gözüne dökülür."""
        print('\n\nSÜRTÜNME GÖÇ MANİFESTOSU (16 Ağu 2026)\n'
              + _tablo_metni(tablo))
        assert len(tablo) == 9
        assert len({s['ad'] for s in tablo}) == 9

    @pytest.mark.parametrize('kayit', MANIFESTO, ids=[k['ad'] for k in MANIFESTO])
    def test_satir_beyani_dogru(self, kayit):
        """eski → yeni → Δ → gerekçe: her sütun ölçümle tutuyor mu?"""
        cozum = _cozum(kayit['vaka'])
        satir = _satir(kayit, cozum)
        assert satir['rejim'] == kayit['rejim'], (
            f"{kayit['ad']}: rejim {kayit['rejim']} bekleniyordu, "
            f"{satir['rejim']} ölçüldü — manifesto vakası kaymış")
        assert satir['kaynak'] == kayit['kaynak'], (
            f"{kayit['ad']}: kaynak beyanı {kayit['kaynak']} olmalıydı, "
            f"{satir['kaynak']} yayımlandı")
        assert any(satir['gerekce'].startswith(s) for s in BEKLENEN_SINIFLAR), (
            f"{kayit['ad']}: gerekçe sınıfı tanınmıyor — göç açıklanmamış")

        if kayit['olculen'] is None:
            # Ölçüm yayımlanamayan vaka: yeni sayı ESKİ SABİTTİR ve bu
            # beyan edilmiştir (sessiz düşüş yok).
            assert satir['olculen'] is None
            assert satir['yeni'] == ESKI_SABIT
            assert satir['itki_yeni_N'] == pytest.approx(
                satir['itki_eski_N'], rel=0.0, abs=0.0)
            not_metni = cozum['losses']['friction_loss_fraction_bl_note']
            assert not_metni and 'shock' in not_metni.lower()
            return

        # Ölçülen vaka: altın değer + Sutton bandı + Δ özdeşlikleri
        assert satir['yeni'] == pytest.approx(kayit['olculen'],
                                              rel=ALTIN_BANT), (
            f"{kayit['ad']}: ölçülen sürtünme kesri {satir['yeni']:.6f}, "
            f"manifestodaki {kayit['olculen']:.6f} değerinden %{ALTIN_BANT * 100:.0f} "
            f"bandının dışında — MODEL KAYMIŞ olabilir, manifestoyu "
            f"gerekçesiyle güncelle")
        assert SUTTON_BANDI[0] < satir['yeni'] < SUTTON_BANDI[1], (
            f"{kayit['ad']}: yeni varsayılan %{100 * satir['yeni']:.3f} "
            f"Sutton & Biblarz bandının ({SUTTON_BANDI}) dışında")
        assert satir['yeni'] == satir['olculen']
        assert satir['delta_mutlak'] == pytest.approx(
            satir['olculen'] - ESKI_VARSAYILAN, rel=0.0, abs=0.0)
        assert satir['delta_bagil'] == pytest.approx(
            satir['delta_mutlak'] / ESKI_VARSAYILAN, rel=1e-15)
        # Yayımlanan Δ alanı manifestoyla AYNI tanımı taşımalı
        assert cozum['losses']['friction_loss_delta_vs_default'] == \
            pytest.approx(satir['delta_mutlak'], rel=0.0, abs=0.0)

    def test_itki_farki_kesirden_geliyor(self, tablo):
        """ΔF, yalnız (1−f) çarpanından gelmeli — el hesabı."""
        for kayit, satir in zip(MANIFESTO, tablo):
            cozum = _cozum(kayit['vaka'])
            kayiplar = cozum['losses']
            beklenen = (kayiplar['divergence_factor']
                        * (1.0 - kayiplar['friction_loss_fraction'])
                        * kayiplar['momentum_thrust_N']
                        + kayiplar['pressure_thrust_N'])
            assert kayiplar['thrust_effective_N'] == pytest.approx(
                beklenen, rel=1e-12), satir['ad']

    def test_gocun_yonu_tek_yonlu_degil(self, tablo):
        """Göç "hep kazanç" DEĞİL: en az bir vakada itki DÜŞMELİ.

        Bu bekçi, "yeni model her zaman daha iyi sayı veriyor" hikâyesini
        imkânsız kılar. Sabitin gizlediği fizik iki yönlüdür.
        """
        artan = [s for s in tablo if s['itki_yeni_N'] > s['itki_eski_N']]
        azalan = [s for s in tablo if s['itki_yeni_N'] < s['itki_eski_N']]
        assert artan, 'hiçbir vakada itki artmıyor — ölçüm şüpheli'
        assert azalan, (
            'hiçbir vakada itki DÜŞMÜYOR — mikro lüle karşı örneği '
            'kaybolmuş olabilir; göç tek yönlü "kazanç" gibi görünüyor')
        assert [s['ad'] for s in azalan] == ['mikro_60bar_eps10']


# ===========================================================================
# (2) ÖLÇEK KURALI — sabitin gizlediği asıl bulgu
# ===========================================================================
class TestOlcekKurali:
    """Ölçülen kayıp boğaz çapıyla düşer; %1,5 sabiti tek noktada doğru.

    ÖLÇÜLDÜ (60 bar, 3200 K, γ = 1,2, MW = 24, ε = 10, vakum):
        D_t [mm]:   5      7,5     10      15      20      30      50     100    250
        f      : 0,01729 0,01627 0,01558 0,01466 0,01403 0,01320 0,01222 0,01097 0,00947
    Yani geçiş çapı ≈ 12 mm. Amatör/öğrenci motorlarının boğazları tam bu
    bandın içindedir — eski sabit orada sürtünmeyi OLDUĞUNDAN AZ gösteriyordu.
    """

    CAPLAR_MM = (5.0, 10.0, 20.0, 50.0, 250.0)
    ORTAK = dict(chamber_pressure=60e5, chamber_temperature=3200.0,
                 gamma=1.2, molecular_weight=24.0, expansion_ratio=10.0,
                 ambient_pressure=0.0)

    @pytest.fixture(scope='class')
    def tarama(self):
        cikti = []
        for d_mm in self.CAPLAR_MM:
            cozum = NozzleFlow1D(throat_diameter=d_mm / 1000.0,
                                 **self.ORTAK).solve()
            cikti.append((d_mm,
                          cozum['losses']['friction_loss_fraction'],
                          cozum['losses']['boundary_layer']))
        return cikti

    def test_kesir_capla_monoton_azalir(self, tarama):
        kesirler = [f for _, f, _ in tarama]
        assert all(a > b for a, b in zip(kesirler, kesirler[1:])), (
            f'ölçülen kesir boğaz çapıyla monoton azalmıyor: {kesirler}')

    def test_kucuk_bogazda_sabit_iyimserdi(self, tarama):
        """5 ve 10 mm boğazda ölçülen kayıp %1,5'in ÜSTÜNDE."""
        for d_mm, kesir, _ in tarama:
            if d_mm <= 10.0:
                assert kesir > ESKI_VARSAYILAN, (
                    f'D_t = {d_mm} mm: ölçülen {kesir:.5f} ≤ eski sabit — '
                    f'karşı örnek kayboldu, manifesto ölçek iddiasını '
                    f'kanıtlayamaz')
            if d_mm >= 20.0:
                assert kesir < ESKI_VARSAYILAN, (
                    f'D_t = {d_mm} mm: ölçülen {kesir:.5f} ≥ eski sabit')

    def test_reynolds_yonu_fizikle_tutarli(self, tarama):
        """Kesir artışının SEBEBİ Re_θ düşüşü olmalı (c_f ~ Re_θ^(−0,268))."""
        re_theta = []
        for d_mm, _, blok in tarama:
            istasyon = blok['stations']
            gecerli = [v for v in istasyon['re_theta_reference']
                       if v is not None and not math.isnan(v)]
            re_theta.append(max(gecerli))
        assert all(a < b for a, b in zip(re_theta, re_theta[1:])), (
            f'boğaz Reynolds sayısı çapla artmıyor: {re_theta}')
        assert re_theta[0] < 1000.0, (
            'en küçük lülede Re_θ zaten yüksek — ölçek iddiası bu vakayla '
            'kurulamaz')


# ===========================================================================
# (3) KAYNAK SÖZLEŞMESİ — hangi sayı neden yayımlandı
# ===========================================================================
REFERANS = dict(chamber_pressure=70e5, chamber_temperature=3500.0,
                gamma=1.2, molecular_weight=24.0, throat_diameter=0.10,
                expansion_ratio=25.0, ambient_pressure=0.0)


class TestKaynakSozlesmesi:
    def test_varsayilan_olcumden(self):
        kayiplar = NozzleFlow1D(**REFERANS).solve()['losses']
        assert kayiplar['friction_loss_fraction_source'] == 'integral_bl_measured'
        assert kayiplar['friction_loss_fraction'] == \
            kayiplar['friction_loss_fraction_integral_bl']
        assert kayiplar['friction_loss_fraction'] != ESKI_SABIT

    def test_kullanici_degeri_kazanir(self):
        kayiplar = NozzleFlow1D(**REFERANS,
                                friction_loss_fraction=0.008
                                ).solve()['losses']
        assert kayiplar['friction_loss_fraction'] == 0.008
        assert kayiplar['friction_loss_fraction_source'] == 'user'
        # Ölçüm YİNE yayımlanır (kullanıcı kendi sayısını denetleyebilsin)
        assert kayiplar['friction_loss_fraction_integral_bl'] is not None
        assert kayiplar['friction_loss_fraction_integral_bl'] != 0.008

    def test_sinir_tabakasi_kapaliyken_yedek_sabit(self):
        kayiplar = NozzleFlow1D(**REFERANS).solve(
            include_boundary_layer=False)['losses']
        assert kayiplar['friction_loss_fraction'] == ESKI_SABIT
        assert kayiplar['friction_loss_fraction_source'] == 'legacy_constant'
        assert 'NO MEASUREMENT AVAILABLE' in \
            kayiplar['friction_loss_fraction_basis']

    def test_bogulmamis_akista_yedek_sabit(self):
        kayiplar = NozzleFlow1D(
            chamber_pressure=1.0e5, chamber_temperature=1200.0, gamma=1.3,
            molecular_weight=28.0, throat_diameter=0.02, expansion_ratio=25.0,
            ambient_pressure=99999.0).solve()['losses']
        assert kayiplar['friction_loss_fraction_source'] == 'legacy_constant'
        assert kayiplar['boundary_layer'] is None

    def test_kaynak_alani_her_zaman_var_ve_bilinen_kumede(self):
        """Beyan alanı boş bırakılamaz (üç vaka, üç kaynak)."""
        gorulen = set()
        for kayit in MANIFESTO:
            kaynak = _cozum(kayit['vaka'])['losses'][
                'friction_loss_fraction_source']
            assert kaynak in ('integral_bl_measured', 'user', 'legacy_constant')
            gorulen.add(kaynak)
        gorulen.add(NozzleFlow1D(**REFERANS, friction_loss_fraction=0.01)
                    .solve()['losses']['friction_loss_fraction_source'])
        assert gorulen == {'integral_bl_measured', 'user', 'legacy_constant'}

    def test_beyan_metni_dogrulama_bandini_tasiyor(self):
        """Yeni varsayılanın künyesi model belirsizliğini SÖYLEMELİ."""
        temel = NozzleFlow1D(**REFERANS).solve()['losses'][
            'friction_loss_fraction_basis']
        for parca in ('MEASURED', 'Blasius', 'Schultz-Grunow',
                      'test_surtunme_gocu.py', '16 Aug 2026'):
            assert parca in temel, f'beyan metninde eksik: {parca}'
        assert len(temel) > 400

    def test_eski_sabit_yanit_icinde_gorunur_kalir(self):
        """Göç denetlenebilir: eski sayı da yayımlanmaya devam eder."""
        kayiplar = NozzleFlow1D(**REFERANS).solve()['losses']
        assert kayiplar['friction_loss_fraction_legacy_constant'] == ESKI_SABIT
        beklenen_eski = (kayiplar['divergence_factor']
                         * (1.0 - ESKI_SABIT)
                         * kayiplar['momentum_thrust_N']
                         + kayiplar['pressure_thrust_N'])
        assert kayiplar['thrust_effective_legacy_constant_N'] == pytest.approx(
            beklenen_eski, rel=1e-12)
        assert kayiplar['CF_effective_legacy_constant'] == pytest.approx(
            beklenen_eski / (70e5 * math.pi * 0.05 ** 2), rel=1e-9)


# ===========================================================================
# (4) ETKİ YARIÇAPI — kaç yaprak oynadı?
# ===========================================================================
#: Göçün DEĞİŞTİRMESİNE İZİN VERİLEN yapraklar. Bu kümenin dışında bir
#: yaprak oynarsa göç "sürtünme kesri" olmaktan çıkmış demektir.
GOCUN_OYNATTIGI_YAPRAKLAR = {
    '.losses.friction_loss_fraction',
    '.losses.friction_loss_fraction_source',
    '.losses.friction_loss_fraction_basis',
    '.losses.thrust_effective_N',
    '.losses.CF_effective',
}


class TestEtkiYaricapi:
    @pytest.mark.parametrize('kayit', MANIFESTO, ids=[k['ad'] for k in MANIFESTO])
    def test_yalniz_bes_yaprak_oynuyor(self, kayit):
        """Yeni varsayılan vs açık 0,015: fark TAM olarak beyan edilen küme.

        'Eski' taraf uydurma değil: kullanıcı üstünlüğü yolundan geçen
        gerçek çözüm — yani göç öncesi davranışın tam kendisi.
        """
        yeni = dict(shake.leaves(_cozum(kayit['vaka'])))
        eski = dict(shake.leaves(
            NozzleFlow1D(**kayit['vaka'],
                         friction_loss_fraction=ESKI_VARSAYILAN).solve()))
        assert set(yeni) == set(eski), 'anahtar kümesi değişmiş'
        oynayan = set(shake.differing_paths(eski, yeni, rel_tol=0.0))
        if kayit['olculen'] is None:
            # Ölçüm yayımlanamayan vakada sayısal fark YOK; yalnız kaynak
            # beyanı ('legacy_constant' vs 'user') ve künye metni ayrışır.
            assert oynayan <= {'.losses.friction_loss_fraction_source',
                               '.losses.friction_loss_fraction_basis'}, oynayan
            return
        assert oynayan == GOCUN_OYNATTIGI_YAPRAKLAR, (
            f"{kayit['ad']}: beklenmeyen yaprak oynadı → "
            f"{sorted(oynayan - GOCUN_OYNATTIGI_YAPRAKLAR)}; "
            f"beklenip oynamayan → "
            f"{sorted(GOCUN_OYNATTIGI_YAPRAKLAR - oynayan)}")
        assert len(yeni) > 1000, (
            f'karşılaştırılan yaprak sayısı düşük ({len(yeni)}) — bekçi '
            f'kör kalmış olabilir')

    def test_performans_blogu_dokunulmadi(self):
        """Ham itki/CF/debi göçten ETKİLENMEZ (kayıp yalnız losses'ta)."""
        yeni = _cozum(REFERANS)['performance']
        eski = NozzleFlow1D(**REFERANS,
                            friction_loss_fraction=ESKI_VARSAYILAN
                            ).solve()['performance']
        assert json.dumps(yeni, sort_keys=True) == \
            json.dumps(eski, sort_keys=True)


# ===========================================================================
# (5) ÜÇ MOTOR UCU — ölçülen etki: SIFIR yaprak
# ===========================================================================
HIBRIT_GOVDE = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
}
KATI_GOVDE = {
    'motor_name': 'surtunme_gocu', 'chamber_pressure': 40, 'thrust': 1500,
    'burn_time': 3, 'grain_type': 'bates', 'outer_diameter': 100,
    'core_diameter': 35, 'grain_length': 300, 'segments': 1,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35, 'chamber_temperature': 3000,
    'c_star': 1550, 'propellant_density': 1800, 'propellant_type': 'apcp',
}
SIVI_GOVDE = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5, 'nozzle_expansion_ratio': 50,
    'max_burn_duration': 400, 'combustion_efficiency': 97,
    'contraction_ratio': 4, 'characteristic_length': 1.2,
    'chamber_wall_thickness': 5, 'cooling_type': 'regenerative',
    'injector_type': 'impinging', 'engine_cycle': 'pressure_fed',
    'safety_factor': 2.5,
}
UC_MOTOR = (('hybrid', '/calculate', HIBRIT_GOVDE),
            ('solid', '/calculate_solid', KATI_GOVDE),
            ('liquid', '/calculate_liquid', SIVI_GOVDE))


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestUcMotorEtkisi:
    """ÖLÇÜLDÜ (16 Ağu 2026): göç üç motor ucunda SIFIR yaprak oynatıyor.

    Sebep yapısaldır: ``/calculate``, ``/calculate_solid`` ve
    ``/calculate_liquid`` zincirleri ``NozzleFlow1D``i HİÇ çağırmıyor
    (sayaçla ölçüldü: 0/0/0). Sıvı motorun teslim-Isp zinciri sabiti
    ``hrma.constants``tan doğrudan okuyor ve o sabitin DEĞERİ değişmedi.
    Bu sınıf iddiayı iki bağımsız yoldan kanıtlar: (a) çağrı sayacı,
    (b) göç yolunu ZEHİRLEYİP yanıtın bit-aynı kalması.
    """

    @pytest.mark.parametrize('ad,uc,govde', UC_MOTOR,
                             ids=[m[0] for m in UC_MOTOR])
    def test_zincir_cozucuyu_cagirmiyor_ve_yanit_bit_ayni(
            self, istemci, monkeypatch, ad, uc, govde):
        temiz = istemci.post(uc, json=govde, headers=shake.HEADERS)
        assert temiz.status_code == 200, temiz.get_data(as_text=True)[:300]
        temiz_yapraklar = dict(shake.leaves(temiz.get_json()))

        cagri = {'n': 0}
        gercek_solve = NozzleFlow1D.solve

        def sayan_solve(self, *args, **kwargs):
            cagri['n'] += 1
            return gercek_solve(self, *args, **kwargs)

        monkeypatch.setattr(NozzleFlow1D, 'solve', sayan_solve)
        zehirli = istemci.post(uc, json=govde, headers=shake.HEADERS)
        assert zehirli.status_code == 200
        assert cagri['n'] == 0, (
            f'{ad}: NozzleFlow1D.solve {cagri["n"]} kez çağrıldı — göçün '
            f'etki yarıçapı artık SIFIR DEĞİL, manifestoyu güncelle')
        oynayan = shake.differing_paths(temiz_yapraklar,
                                        dict(shake.leaves(zehirli.get_json())),
                                        rel_tol=0.0)
        assert oynayan == [], oynayan[:10]

    @pytest.mark.parametrize('ad,uc,govde', UC_MOTOR,
                             ids=[m[0] for m in UC_MOTOR])
    def test_yanitta_surtunme_kesri_yapragi_yok(self, istemci, ad, uc, govde):
        """Motor yanıtlarında bu göçe ait yaprak HİÇ yok (ölçüldü)."""
        yapraklar = dict(shake.leaves(
            istemci.post(uc, json=govde, headers=shake.HEADERS).get_json()))
        ilgili = [y for y in yapraklar
                  if 'friction_loss_fraction' in y or 'thrust_effective' in y]
        assert ilgili == [], (
            f'{ad}: göç yaprağı motor yanıtına sızmış → {ilgili[:5]}')

    def test_akis_ucu_yeni_sozlesmeyi_yayimliyor(self, istemci):
        """/api/flow-analysis: alan gönderilmezse ÖLÇÜM, gönderilirse kullanıcı."""
        govde = {'chamber_pressure': 70, 'chamber_temperature': 3500,
                 'gamma': 1.2, 'molecular_weight': 24.0,
                 'throat_diameter': 0.10, 'expansion_ratio': 25.0,
                 'ambient_pressure': 0.0}
        yanit = istemci.post('/api/flow-analysis', json=govde, headers=shake.HEADERS)
        assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
        kayiplar = yanit.get_json()['flow']['losses']
        assert kayiplar['friction_loss_fraction_source'] == 'integral_bl_measured'
        assert kayiplar['friction_loss_fraction'] == pytest.approx(
            0.013801691, rel=ALTIN_BANT)

        kullanici = istemci.post('/api/flow-analysis',
                                 json=dict(govde, friction_loss_fraction=0.02),
                                 headers=shake.HEADERS)
        assert kullanici.status_code == 200
        kayiplar_k = kullanici.get_json()['flow']['losses']
        assert kayiplar_k['friction_loss_fraction'] == 0.02
        assert kayiplar_k['friction_loss_fraction_source'] == 'user'


# ===========================================================================
# (6) GERİ DÖNÜŞ YOLU — göç öncesi sayılar hâlâ üretilebilir
# ===========================================================================
class TestGeriDonusYolu:
    def test_acik_sabitle_goc_oncesi_altin_sayilar(self):
        """v2.6.27 (göç öncesi) referans vakasının BİT-AYNI sayıları.

        Altın değerler ``tests/flow/test_sinir_tabakasi.py``ın göç öncesi
        sürümünden alındı (98237.33697442376 / 101290.31988066863).
        """
        cozum = NozzleFlow1D(**REFERANS,
                             friction_loss_fraction=0.015).solve()
        assert cozum['losses']['thrust_effective_N'] == pytest.approx(
            98237.33697442376, rel=1e-12)
        assert cozum['performance']['thrust_N'] == pytest.approx(
            101290.31988066863, rel=1e-12)

    def test_yedek_sabitin_degeri_degismedi(self):
        """Sabitin KENDİSİ dokunulmaz — göç varsayılanı taşıdı, değeri değil.

        Sıvı motor teslim-Isp zinciri (liquid_rocket_engine eta_f) hâlâ bu
        sabiti okuyor; değeri değiştirmek o zinciri de sessizce oynatırdı.
        """
        assert ESKI_SABIT == 0.015

    def test_yeni_varsayilan_gocten_once_yayimlanan_sayidan_farkli(self):
        """Göç GERÇEKTEN oldu mu? (sessiz "hiçbir şey değişmedi" tuzağı)"""
        cozum = _cozum(REFERANS)
        assert cozum['losses']['thrust_effective_N'] != pytest.approx(
            98237.33697442376, rel=1e-9)
        assert cozum['losses']['thrust_effective_N'] == pytest.approx(
            98350.487239, rel=ALTIN_BANT)
