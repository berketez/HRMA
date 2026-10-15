# -*- coding: utf-8 -*-
"""ÖH Dalga-26 · hibrit · aşama 1 — dört kalemin bekçileri.

Kalemler
--------
**OH-D25-15** — ``REGRESSION_EXPONENT_VALID`` üst ucu DIŞLAYICI idi: n = 1,0
tam değeri 422 ile reddediliyordu. Bandın kendi gerekçesi "regresyonun akıdan
HIZLI büyümesi"ni reddeder; türetimle o koşul **n > 1**'dir:

    r/G = a·G^(n-1)   =>   d(r/G)/dG = a·(n-1)·G^(n-2)

işaret yalnız n > 1'de pozitiftir ve n = 1'de TAM SIFIRDIR — n = 1 akıyla
tam orantılı NÖTR sınırdır, reddedilen bölgenin içi değil kenarıdır.
"Entegrasyon ıraksar" gerekçesi de tutmaz: G ∝ D⁻² ile dD/dt ∝ D^(-2n) ve
D(t) ∝ t^(1/(2n+1)); n = 1 için D ∝ t^(1/3), her sonlu t'de sonlu. Boyutça da
tekillik yok: [a] = (m/s)/(kg·m⁻²·s⁻¹)^n, n = 1'de m³/kg.

ÖLÇÜLDÜ (``once.json``): n = 0,999999 KABUL, r_dot = 0,012879924550041959 m/s;
n = 1,000000 -> 422 ``non_physical_regression_input`` / ``regression_n``.
Girdideki 1e-6 bağıl adım, sayısal olarak ayırt edilemeyen iki cevaptan
birini yayımlayıp diğerini reddediyordu.

**P14M2-05 / P14M2-05b** — ``hybrid_rocket_engine`` enjektör ΔP'sini ÇIPLAK
``0.2 * self.P_c`` ile kuruyordu (P14 mutasyon raporu §P14M2-05: 10× bozulma,
tek kırmızı ve o da sabit-yaprak SAYACI; ΔP okuyan iki bekçi totolojik).
ÖLÇÜLDÜ (``once.json``): kanonik eşik koşum sırasında 0,40'a ÇEKİLDİĞİNDE de
0,02'ye DÜŞÜRÜLDÜĞÜNDE de ΔP 4,0 barda (0,2·Pc) çakılı kaldı — türetme İKİ
YÖNDE de yoktu (05 sıkma, 05b gevşetme). Bu dosyanın bekçileri değer
eşitliğine DEĞİL TÜRETMEYE bakar ve iki yönü AYRI AYRI sayar.

**OH-B4-04** — 'modelled' blowdown bloğu FAZ kanalını alan olarak
yayımlamıyordu: 36 anahtarın hiçbiri ``phase`` / ``tail_off`` /
``vapor_transition`` desenine uymuyordu, bilgi yalnız geçiş anında doğan bir
uyarı METNİNE ("IDEAL-GAS TAIL-OFF") gömülüydü. Çözücü fazı zaten okuyordu
(yanmayı ``tank.phase == 'vapor'`` ile bitiriyor) ama dışarı vermiyordu.
"""

import ast
import os
import sys
import warnings

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis import acoustic_modes                     # noqa: E402
from hrma.analysis import regression_analysis as ra          # noqa: E402
from hrma.engines import hybrid_rocket_engine as hre         # noqa: E402
from hrma.analysis.regression_analysis import (              # noqa: E402
    NonPhysicalRegressionInput,
    REGRESSION_EXPONENT_BAND_INCLUSIVE,
    REGRESSION_EXPONENT_VALID,
    RegressionAnalyzer,
)

HYBRID_PY = os.path.join(REPO_ROOT, 'hrma', 'engines',
                         'hybrid_rocket_engine.py')

#: Ölçüm tabanı: P14 raporunun ve ``once.json``un kullandığı fit.
FIT_A = 3.68e-5
FIT_G = 350.0


def _hibrit(**degisiklik):
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = hre.HybridRocketEngine(**ayarlar)
        return motor, motor.calculate()


@pytest.fixture(scope='module')
def hibrit_taban():
    return _hibrit()


# ===========================================================================
# OH-D25-15 — regresyon üssü bandının ÜST UCU kapsayıcı
# ===========================================================================
class TestOHD2515UstUcKapsayici:

    def test_n_bir_TAM_degeri_artik_KABUL(self):
        """ÖLÇÜLEN KUSUR: n = 1,0 -> 422. Şimdi eğri üretilmeli."""
        d = RegressionAnalyzer.regression_rate(FIT_A, 1.0, FIT_G)
        assert d['r_dot'] > 0.0
        assert d['r_dot'] == pytest.approx(FIT_A * FIT_G, rel=1e-12), (
            'n = 1 tam orantılı daldır: r = a·G olmak ZORUNDA')

    def test_ust_ucta_SUREKSIZLIK_kalmadi(self):
        """Bandın asıl kusuru buydu: 1e-6'lık girdi adımı hükmü çeviriyordu.

        ÖLÇÜLDÜ (``once.json``): n = 0,999999 -> KABUL,
        r_dot = 0,012879924550041959 m/s;  n = 1,0 -> 422. İki cevap
        sayısal olarak ayırt edilemezdi.
        """
        alt = RegressionAnalyzer.regression_rate(FIT_A, 0.999999, FIT_G)
        ust = RegressionAnalyzer.regression_rate(FIT_A, 1.0, FIT_G)
        assert ust['r_dot'] == pytest.approx(alt['r_dot'], rel=1e-5), (
            'sınırın iki yanı sayısal olarak ayrışmış — ölçüm zemini değişti')

    @pytest.mark.parametrize('n', [1.0000001, 1.05, 1.5, 12.0])
    def test_bir_ustu_HALA_reddediliyor(self, n):
        """Gevşeme YOK: reddedilen bölge (n > 1) aynen reddediliyor."""
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer.regression_rate(FIT_A, n, FIT_G)
        assert ex.value.field == 'regression_n'

    @pytest.mark.parametrize('n', [0.0, -1e-9, -0.555])
    def test_ALT_uc_DISLAYICI_kaldi(self, n):
        """Asimetri kasıtlıdır: alt uç bir İŞARET koşuludur, kapsayıcı olamaz.

        n = 0'da regresyon akıdan tamamen bağımsızlaşır (modelin tanımlayıcı
        içeriği yok olur), n < 0'da ters döner.
        """
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer.regression_rate(FIT_A, n, FIT_G)
        assert ex.value.field == 'regression_n'

    def test_kapsayicilik_TEK_KAYNAK_ve_kapi_onu_okuyor(self):
        """Kapı kendi kopyasını tutmaz: bant + kapsayıcılık tek yerde.

        Bekçi ikiliyi koşum sırasında ÇEVİRİR: üst uç dışlayıcı yapılınca
        n = 1,0 yeniden reddedilmek ZORUNDA. Kapı sabiti okumuyor olsaydı
        (çıplak ``<`` geri gelseydi) bu iddia kırmızı verirdi.
        """
        assert REGRESSION_EXPONENT_BAND_INCLUSIVE == (False, True)
        assert REGRESSION_EXPONENT_VALID == (0.0, 1.0)
        eski = ra.REGRESSION_EXPONENT_BAND_INCLUSIVE
        try:
            ra.REGRESSION_EXPONENT_BAND_INCLUSIVE = (False, False)
            with pytest.raises(NonPhysicalRegressionInput):
                RegressionAnalyzer.regression_rate(FIT_A, 1.0, FIT_G)
        finally:
            ra.REGRESSION_EXPONENT_BAND_INCLUSIVE = eski
        # Geri yazıldı: n = 1,0 yine geçiyor.
        assert RegressionAnalyzer.regression_rate(
            FIT_A, 1.0, FIT_G)['r_dot'] > 0.0

    def test_ret_METNI_de_kapsayiciligi_soyluyor(self):
        """Beyan gerçeği söyler: mesaj hâlâ "strictly inside" diyemez."""
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer.regression_rate(FIT_A, 2.0, FIT_G)
        istek = ex.value.requirement
        assert 'strictly inside' not in istek, istek
        assert '0.0, 1.0]' in istek, istek

    def test_uc_HTTP_yuzunde_de_ayni(self):
        """Kütüphane ile uç aynı hükmü verir (kanon tek)."""
        from hrma.app import app
        istemci = app.test_client()
        govde = {'burn_time': 10.0, 'mdot_ox': 0.38,
                 'port_diameter_initial': 0.037, 'fuel_type': 'htpb'}
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': dict(govde, regression_n=1.0)})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        r2 = istemci.post('/api/regression-analysis',
                          json={'motor_data': dict(govde,
                                                   regression_n=1.0000001)})
        assert r2.status_code == 422
        assert r2.get_json()['error'] == 'non_physical_regression_input'


# ===========================================================================
# P14M2-05 (+05b) — hibrit enjektör ΔP'si TÜRETİLİYOR mu? (İKİ YÖN)
# ===========================================================================
def _dp_orani(oran=None):
    """Kanonik eşik ``oran``a çevrilip motor kurulur; ΔP/Pc ölçülür.

    Eşik iki adla görünüyor (kaynak modül + hibritin ithal ettiği ad);
    türetme gerçekse ikisini birden çevirmek ΔP'yi kıpırdatır. Geri yazım
    ``finally`` içindedir — bekçi kendi ortamını bozup bırakmaz.
    """
    eski_am = acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    eski_hre = hre.CHUG_DP_RATIO_RECOMMENDED
    try:
        if oran is not None:
            acoustic_modes.CHUG_DP_RATIO_RECOMMENDED = oran
            hre.CHUG_DP_RATIO_RECOMMENDED = oran
        motor, _ = _hibrit()
        return float(motor._inj_delta_P) / float(motor.P_c)
    finally:
        acoustic_modes.CHUG_DP_RATIO_RECOMMENDED = eski_am
        hre.CHUG_DP_RATIO_RECOMMENDED = eski_hre


class TestP14M205EnjektorDPTuretmesi:

    def test_taban_orani_kanonik_esikle_AYNI(self):
        """Göç sessiz sayı değişikliği DEĞİLDİR: bugünkü oran 0,20 kalır."""
        assert _dp_orani() == pytest.approx(
            acoustic_modes.CHUG_DP_RATIO_RECOMMENDED, rel=1e-12)

    def test_SIKMA_yonu_turetiliyor(self):
        """P14M2-05: eşik 0,40'a çekilince ΔP de çıkmalı.

        ÖLÇÜLDÜ (``once.json``): çıplak literalle ΔP 4,0 barda (0,2·Pc)
        kaldı; hiçbir bekçi bunu görmüyordu (tek kırmızı sabit-yaprak
        SAYACIYDI ve teşhisi yanlış yere gösteriyordu).
        """
        assert _dp_orani(0.40) == pytest.approx(0.40, rel=1e-12), (
            'ΔP eşikten türetilmiyor — çıplak 0,2 literali geri gelmiş '
            'olabilir (sıkma yönü)')

    def test_GEVSETME_yonu_de_turetiliyor(self):
        """P14M2-05b: kusurun tesadüfi tek kırmızısı YÖN BAĞIMLIYDI.

        P14 raporu: gevşetme yönünde 92 test 0 kırmızı verdi. Bir bekçi
        ancak kusurun KENDİ yönünde de kırmızıya dönüyorsa bekçidir.
        """
        assert _dp_orani(0.02) == pytest.approx(0.02, rel=1e-12), (
            'ΔP eşikten türetilmiyor — çıplak 0,2 literali geri gelmiş '
            'olabilir (gevşetme yönü)')

    def test_enjeksiyon_HIZI_da_esikle_birlikte_kayiyor(self):
        """Zincir kopmasın: v = sqrt(2·ΔP/ρ) da eşiği izlemeli.

        Kusurun ürün yüzündeki bedeli buydu — P14 ölçümü 10× ΔP için
        3,16× enjeksiyon hızı saydı.
        """
        eski_am = acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
        eski_hre = hre.CHUG_DP_RATIO_RECOMMENDED
        try:
            motor0, _ = _hibrit()
            v0 = float(motor0._inj_velocity)
            acoustic_modes.CHUG_DP_RATIO_RECOMMENDED = 4.0 * eski_am
            hre.CHUG_DP_RATIO_RECOMMENDED = 4.0 * eski_am
            motor1, _ = _hibrit()
            v1 = float(motor1._inj_velocity)
        finally:
            acoustic_modes.CHUG_DP_RATIO_RECOMMENDED = eski_am
            hre.CHUG_DP_RATIO_RECOMMENDED = eski_hre
        assert v1 / v0 == pytest.approx(2.0, rel=1e-9), (
            f'ΔP 4× iken hız 2× olmalı (Bernoulli); ölçülen {v1 / v0}')

    def test_hibritte_ciplak_chug_esigi_kalmadi(self):
        """AST: 0,15/0,20 çifti bu dosyada SAYI olarak yaşamıyor.

        Muafiyet GEREKÇELİDİR ve tektir: ``OF_SHIFT_WARN_FRACTION`` bir
        ΔP/Pc oranı değil, O/F KAYMASI uyarı eşiğidir (kendi adı, kendi
        künyesi). Gerekçesiz muafiyet yoktur.
        """
        semantik_disi = {'OF_SHIFT_WARN_FRACTION'}
        kaynak = open(HYBRID_PY, encoding='utf-8').read()
        satirlar = kaynak.split('\n')
        ebeveyn = {}
        agac = ast.parse(kaynak, filename=HYBRID_PY)
        for ust in ast.walk(agac):
            for cocuk in ast.iter_child_nodes(ust):
                ebeveyn[cocuk] = ust
        ihlaller = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Constant):
                continue
            v = dugum.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if not any(abs(v - h) < 1e-12 for h in (0.15, 0.20)):
                continue
            sahip, n = None, dugum
            while n in ebeveyn:
                ust = ebeveyn[n]
                if isinstance(ust, ast.Assign):
                    for hedef in ust.targets:
                        if isinstance(hedef, ast.Name):
                            sahip = hedef.id
                        elif isinstance(hedef, ast.Attribute):
                            sahip = hedef.attr
                    break
                n = ust
            if sahip in semantik_disi:
                continue
            ihlaller.append(
                f'  :{dugum.lineno} [{sahip}] = {v}  '
                f'{satirlar[dugum.lineno - 1].strip()[:90]}')
        assert not ihlaller, (
            'chug ΔP/Pc eşiği hibrit dosyasında SAYI olarak yaşıyor:\n'
            + '\n'.join(ihlaller)
            + '\nTek tanım yeri hrma/analysis/acoustic_modes.py — ithal et.')
        assert 'CHUG_DP_RATIO_RECOMMENDED' in kaynak, (
            'hibrit dosyası kanonik eşiği artık ithal etmiyor')

    def test_yedek_dal_da_tek_kaynaktan_okuyor(self):
        """``dp_ratio_ox`` yedeği de çıplak 0,20 taşıyordu.

        Ölçüm: kaynakta ``else 0.20`` geçişi vardı; artık sabitten okunur.
        """
        kaynak = open(HYBRID_PY, encoding='utf-8').read()
        assert 'else 0.20,' not in kaynak
        assert 'else CHUG_DP_RATIO_RECOMMENDED' in kaynak


# ===========================================================================
# OH-B4-04 — blowdown bloğunun FAZ KANALI (borç imi kaldırıldı)
# ===========================================================================
#: Faz kanalı aranırken kullanılan desenler — S2 bekçisiyle AYNI küme.
FAZ_DESENLERI = ('phase', 'tail_off', 'vapor_transition')


class TestOHB404FazKanali:

    def test_blok_faz_kanalini_ALAN_olarak_yayimliyor(self, hibrit_taban):
        """ÖLÇÜLEN KUSUR: 36 anahtar, faz deseni eşleşen alan sayısı 0."""
        blok = hibrit_taban[1]['tank_blowdown']
        assert blok['status'] == 'modelled'
        alanlar = [a for a in blok
                   if any(d in a.lower() for d in FAZ_DESENLERI)]
        assert 'tank_phase' in alanlar and 'tank_phase_final' in alanlar, (
            f'faz kanalı yayımlanmıyor (blok anahtarları: {sorted(blok)})')

    def test_faz_serisi_zaman_ekseniyle_HIZALI(self, hibrit_taban):
        """Seri seyreltmesi zamanla AYNI ``idx``ten geçmeli."""
        blok = hibrit_taban[1]['tank_blowdown']
        assert len(blok['tank_phase']) == len(blok['time_s'])
        assert len(blok['tank_phase']) > 1

    def test_faz_DEGERLERI_tankin_kendi_kumesinden(self, hibrit_taban):
        """Uydurma etiket yok: değerler tankın ``self.phase`` kümesinden."""
        from hrma.analysis import tank_blowdown as tb_mod
        gecerli = set()
        for dugum in ast.walk(ast.parse(
                open(os.path.join(REPO_ROOT, 'hrma', 'analysis',
                                  'tank_blowdown.py'),
                     encoding='utf-8').read())):
            if (isinstance(dugum, ast.Assign)
                    and isinstance(dugum.value, ast.Constant)
                    and isinstance(dugum.value.value, str)):
                for h in dugum.targets:
                    if (isinstance(h, ast.Attribute) and h.attr == 'phase'
                            and isinstance(h.value, ast.Name)
                            and h.value.id == 'self'):
                        gecerli.add(dugum.value.value)
        assert gecerli >= {'two_phase', 'vapor'}, sorted(gecerli)
        assert tb_mod is not None
        blok = hibrit_taban[1]['tank_blowdown']
        disarida = set(blok['tank_phase']) - gecerli
        assert not disarida, f'faz serisinde tanksız etiket: {disarida}'
        assert blok['tank_phase_final'] in gecerli

    def test_son_faz_ve_end_event_TUTARLI(self, hibrit_taban):
        """Kanal ``end_event`` ile çelişemez.

        ``oxidizer_depleted`` tam olarak "tank buhar fazına geçti" demektir
        (çözücü döngüsü bu koşulla kırılır) — o hâlde son faz 'vapor' ve
        geçiş anı bir SAYI olmak zorundadır; başka bir sonlanmada geçiş anı
        None kalır ve sayı UYDURULMAZ.
        """
        blok = hibrit_taban[1]['tank_blowdown']
        if blok['end_event'] == 'oxidizer_depleted':
            assert blok['tank_phase_final'] == 'vapor'
            assert blok['vapor_onset_s'] is not None
            assert blok['vapor_onset_s'] > blok['time_s'][-1]
        else:
            assert blok['vapor_onset_s'] is None

    def test_gecis_ani_kuyruk_uyarisiyla_AYNI_OLAYI_anlatiyor(
            self, hibrit_taban):
        """Alan, uyarı metninin söylediği olayı ADIYLA taşımalı."""
        blok = hibrit_taban[1]['tank_blowdown']
        uyarilar = blok.get('warnings') or []
        kuyruk = [u for u in uyarilar if 'TAIL-OFF' in u]
        if kuyruk:
            assert blok['tank_phase_final'] == 'vapor', (
                'kuyruk uyarısı var ama faz alanı sıvı diyor — iki kanal '
                'çelişiyor')

    def test_kunye_alani_kanali_ACIKLIYOR(self, hibrit_taban):
        """Beyan gerçeği söyler ve alan adlarını içerir."""
        blok = hibrit_taban[1]['tank_blowdown']
        kunye = blok['tank_phase_basis']
        for ad in ('two_phase', 'vapor', 'tank_phase_final',
                   'vapor_onset_s'):
            assert ad in kunye, ad

    def test_cozucu_fazi_KENDI_adim_kaydindan_veriyor(self, hibrit_taban):
        """Tek kaynak: blok fazı yeniden türetmez, çözücüden okur."""
        motor = hibrit_taban[0]
        from hrma.analysis.transient_ballistics import TransientBallistics
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            tb = TransientBallistics(
                motor, feed_mode='blowdown',
                tank_temperature=hre.TANK_TEMPERATURE_DEFAULT_K,
                liquid_fill_fraction=hre.TANK_FILL_FRACTION_DEFAULT,
                n_steps=hre.TANK_BLOWDOWN_N_STEPS)
            sol = tb.solve()
        assert 'tank_phase' in sol and 'tank_phase_final' in sol
        assert len(sol['tank_phase']) == len(sol['time'])
        assert sol['tank_phase_final'] == tb.tank.phase

    def test_reguleli_kipte_faz_serisi_UYDURULMUYOR(self, hibrit_taban):
        """Tank yoksa seri boştur ve son faz None'dır (fail-closed)."""
        motor = hibrit_taban[0]
        from hrma.analysis.transient_ballistics import TransientBallistics
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            tb = TransientBallistics(motor, feed_mode='regulated')
            sol = tb.solve()
        assert sol['tank_phase'] == []
        assert sol['tank_phase_final'] is None
        assert sol['vapor_onset_s'] is None
