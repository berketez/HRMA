# -*- coding: utf-8 -*-
"""ÖH D28 / hibrit aşama-1 bekçileri — OH-D27-09.

Ölçüm ve kanıt: ``docs/scofield/raw/OH/D28/hibrit/a1/`` (``olcum.py``,
``once.json``, ``sonra.json``, ``mutasyon.py``, ``mutasyon.json``,
``rapor.md``).

KALEM — OH-D27-09 (hüküm-16 bulgusu, D27 hibrit a1 zarf taramasından)
---------------------------------------------------------------------
Başlık: "Hibrit blowdown: ``TransientBallistics.solve`` yürüyüşü
``tank.phase == 'vapor'`` anında duruyor, buhar fazı integre edilmiyor →
üçlü nokta / buhar zarfı kapısı YAPISAL OLARAK True (künye beyan ediyor)."

ÖLÇÜLDÜ (``once.json``, taban ``7cd08bcc``, altı senaryoluk ızgara):

* K1 — altı koşunun ALTISINDA da ``integre_buhar_adimi = 0``,
  ``vapor_model_valid = True``, ``end_event = 'oxidizer_depleted'``.
  Blok 43 anahtar yayımlıyor ve içlerinde artık/kuyruk payını veren
  ``residual`` / ``tail_off`` desenli **0** alan var.
* K2 — kesme SESSİZ değil, ÖLÇÜSÜZDÜ: sıvı bittiğinde tankta kalan
  oksitleyici nominalde **0,529 kg**, son integre adımın
  oksitleyici-özgül impulsuyla (F/ṁ_ox) değerlendiğinde **1.256 N·s**,
  yani yayımlanan toplam impulsun **%14,1**'i. Altı senaryoda pay
  %3,6-%19,0 bandında. Hiçbir alandan okunamıyordu.
* K3 — kapı yalnız "ateşlenmemiş" değil, ateşlenmesi GEREKEN bir kapıydı:
  kuyruk yolu yalnız kalan kütle oranıyla parametreli olduğundan
  (``P/P0 = r^γ``, ``T/T0 = r^(γ-1)``) üçlü nokta geçişi debi modeli
  OLMADAN karara bağlanır. Altı senaryonun altısında da
  ``r_akış_durur < r_üçlü_nokta`` (nominal 0,0659 < 0,2222): yürünmeyen
  kuyruk, tankın kendi modelinin geçerlilik zarfını terk ederdi.

ÜRÜN KARARI (kalemin iki şıkkından ikincisi, ama ÖLÇÜLMÜŞ hâli): kuyruk
fazı bu çözücüde İNTEGRE EDİLMEZ — K3 gösteriyor ki integre etmek, zarfı
terk etmiş bir modelden itki yayımlamak olurdu (üstüne sıvı için kalibre
edilmiş SPI enjektörünü buhara uygulamak gerekirdi). Karşılığında:

1. Kesmenin boyu SAYIYLA yayımlanır (``residual_oxidizer_kg``,
   ``residual_impulse_at_cutoff_rate_Ns``,
   ``residual_impulse_fraction_at_cutoff_rate``).
2. "Buhar adımı integre edilmedi" hükmü ÖLÇÜLÜR (``vapor_phase_integrated``,
   kayıtlı faz serisinden), varsayılmaz.
3. Zarf kapısı ateşlenebilir hâle gelir
   (``vapor_tail_off_leaves_model_envelope``) ve kesmenin GEREKÇESİ olur.
4. Metin kanalı da susmaz: ``warnings`` içinde "TRUNCATED TAIL-OFF"
   satırı üç sayıyı da taşır (paneller ``warnings`` rozetlerini basıyor).

SONRA (``sonra.json``): blok 48 anahtar; artık deseni eşleşen alan 0 → 4
(+ ``vapor_phase_integrated``); ``vapor_tail_off_leaves_model_envelope``
altı senaryonun altısında da True.
"""
import ast
import contextlib
import io
import math
import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:                                   # pragma: no cover
    sys.path.insert(0, KOK)

from hrma.analysis.tank_blowdown import (                 # noqa: E402
    N2O_GAMMA_VAPOR, N2O_P_TRIPLE, N2O_T_TRIPLE, N2OTankBlowdown)
from hrma.analysis.transient_ballistics import (          # noqa: E402
    TransientBallistics)
from hrma.engines.hybrid_rocket_engine import (           # noqa: E402
    HybridRocketEngine, TANK_BLOWDOWN_N_STEPS,
    TANK_FILL_FRACTION_DEFAULT, TANK_TEMPERATURE_DEFAULT_K)

#: Ölçüm betiğiyle (``olcum.py``) BİREBİR aynı taban gövde.
_MOTOR_TABANI = dict(thrust=1000, burn_time=10, of_ratio=6.0,
                     chamber_pressure=20.0, fuel_type='htpb',
                     oxidizer_type='n2o', expansion_ratio=8,
                     atmospheric_pressure=1.0)

#: Kesilen payı adlandıran alanlar — ``once.json`` bu desende 0 alan buldu.
ARTIK_ALANLARI = ('residual_oxidizer_kg',
                  'residual_impulse_at_cutoff_rate_Ns',
                  'residual_impulse_fraction_at_cutoff_rate')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**ek):
    m = _sessiz(HybridRocketEngine, **dict(_MOTOR_TABANI, **ek))
    _sessiz(m.calculate)
    return m


@pytest.fixture(scope='module')
def taban_motor():
    return _motor()


@pytest.fixture(scope='module')
def blok(taban_motor):
    return _sessiz(taban_motor._tank_blowdown_block)


@pytest.fixture(scope='module')
def cozum(taban_motor):
    tb = _sessiz(TransientBallistics, taban_motor, feed_mode='blowdown',
                 tank_temperature=TANK_TEMPERATURE_DEFAULT_K,
                 liquid_fill_fraction=TANK_FILL_FRACTION_DEFAULT,
                 n_steps=TANK_BLOWDOWN_N_STEPS)
    return tb, _sessiz(tb.solve)


# ===========================================================================
# 1) Kesilen pay ARTIK ÖLÇÜLÜ — kalemin ta kendisi
# ===========================================================================
class TestOHD2709KesilenPayYayimlaniyor:

    def test_kesme_payi_ALAN_olarak_var(self, blok):
        """ÖLÇÜLEN KUSUR: 43 anahtar, artık payı deseni eşleşen alan 0."""
        assert blok['status'] == 'modelled', blok.get('reason')
        eksik = [ad for ad in ARTIK_ALANLARI if ad not in blok]
        assert not eksik, (
            'OH-D27-09 geri açılmış: yürüyüş sıvı bitince duruyor ama '
            f'kesilen payı veren alan(lar) yok: {eksik} '
            f'(blok anahtarları: {sorted(blok)})')

    def test_kesme_payi_SAYI_tasiyor_ve_sifir_degil(self, blok):
        """Boş bir alan borcu ödemez: pay gerçekten ölçülmüş olmalı."""
        assert blok['end_event'] == 'oxidizer_depleted', (
            'ölçüm zemini değişti: nominal koşu artık sıvı tükenerek '
            f"bitmiyor ({blok['end_event']})")
        m_kalan = blok['residual_oxidizer_kg']
        i_kalan = blok['residual_impulse_at_cutoff_rate_Ns']
        oran = blok['residual_impulse_fraction_at_cutoff_rate']
        for ad, deger in (('residual_oxidizer_kg', m_kalan),
                          ('residual_impulse_at_cutoff_rate_Ns', i_kalan),
                          ('residual_impulse_fraction_at_cutoff_rate', oran)):
            assert isinstance(deger, float), f'{ad} sayı değil: {deger!r}'
            assert math.isfinite(deger) and deger > 0.0, (
                f'{ad} boş/sıfır: kesme ölçülmemiş ({deger})')
        # once.json nominal: 0,529 kg -> 1.256 N·s -> %14,1. Çapa GEVŞEK
        # tutuluyor (motor zinciri kayarsa bant kayar) ama payın büyüklük
        # mertebesi kilitli: bu bir "birkaç promil" artık DEĞİLDİR.
        assert 0.02 < oran < 0.60, (
            f'kesilen pay oranı ölçülen banttan çıktı: {oran:.4f} '
            '(once.json: 0,0357-0,1900)')

    def test_pay_kimlikle_TUTARLI_uydurma_degil(self, blok, cozum):
        """I = m_kalan · (F/ṁ_ox)_kesim kimliği ÇÖZÜCÜ dizilerinden tutar.

        Sayı bir yerden "gelmiş" olamaz: üç çarpanın üçü de çözümün kendi
        son adımından okunur. Kimlik bozulursa alan uydurma bir sayıya
        döner.
        """
        tb, sol = cozum
        oran_son = float(sol['thrust'][-1]) / float(sol['mdot_ox'][-1])
        beklenen = blok['residual_oxidizer_kg'] * oran_son
        assert blok['residual_impulse_at_cutoff_rate_Ns'] == pytest.approx(
            beklenen, rel=1e-12), (
            'artık impuls, son adımın oksitleyici-özgül impulsuyla '
            'hesaplanmıyor — kimlik koptu')
        assert blok['residual_impulse_fraction_at_cutoff_rate'] == (
            pytest.approx(beklenen / blok['total_impulse_Ns'], rel=1e-12))

    def test_kalan_kutle_TANKIN_kendi_defterinden(self, blok, cozum):
        """Tek kaynak: kalan oksitleyici tankın kütle defterinden okunur."""
        tb, _sol = cozum
        assert blok['residual_oxidizer_kg'] == pytest.approx(
            float(tb.tank.liquid_mass + tb.tank.vapor_mass), rel=1e-12), (
            'kalan oksitleyici tank nesnesinden okunmuyor')

    def test_urun_kaynaginda_SABIT_yazilmamis(self):
        """AST ayağı: beş alanın hiçbiri sabit değil, çözümden okunuyor.

        M2 dersi (ÖH D27 / P13B4-04): koşum ayağı tek başına yetmez —
        yapısal olarak aynı sayıyı veren bir sabit koşumda ayırt edilemez.
        """
        yol = os.path.join(KOK, 'hrma', 'engines', 'hybrid_rocket_engine.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        bulunan = {}
        aranan = set(ARTIK_ALANLARI) | {'vapor_phase_integrated',
                                        'vapor_tail_off_leaves_model_envelope'}
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Dict):
                continue
            for k, v in zip(dugum.keys, dugum.values):
                if isinstance(k, ast.Constant) and k.value in aranan:
                    bulunan[k.value] = v
        for ad in sorted(aranan):
            v = bulunan.get(ad)
            assert v is not None, f'{ad} ürün kaynağında yayımlanmıyor'
            assert not isinstance(v, ast.Constant), (
                f'{ad} SABİT yazılmış: değer çözümden okunmuyor '
                '(doktrin 4/6)')
            adlar = {d.id for d in ast.walk(v) if isinstance(d, ast.Name)}
            assert 'sol' in adlar, (
                f'{ad} çözücünün dönüşünden okunmuyor: {ast.dump(v)[:120]}')


# ===========================================================================
# 2) "Buhar adımı integre edilmedi" hükmü ÖLÇÜLÜR
# ===========================================================================
class TestOHD2709IntegrasyonHukmuOlculuyor:

    def test_hukum_kayitli_faz_serisinden_geliyor(self, cozum):
        """``vapor_phase_integrated`` varsayım değil ÖLÇÜM.

        Faz serisi çözücünün kendi adım kaydıdır; hüküm onun üzerinden
        kurulur. Kayıtta 'vapor' varsa hüküm True olmak ZORUNDADIR.
        """
        _tb, sol = cozum
        kayitli = any(f == 'vapor' for f in sol['tank_phase'])
        assert sol['vapor_phase_integrated'] is kayitli, (
            'hüküm faz kaydıyla çelişiyor — sabit yazılmış olabilir')

    def test_bugun_hicbir_buhar_adimi_integre_EDILMIYOR(self, blok, cozum):
        """once.json K1: altı senaryonun altısında da 0 buhar adımı."""
        _tb, sol = cozum
        assert blok['vapor_phase_integrated'] is False, (
            'yürüyüş artık buhar fazına giriyor — OH-D27-09 zemini '
            'değişti, künye ve kesme payı yeniden ölçülmeli')
        assert sol['tank_phase_final'] == 'vapor', (
            'sıvı tükenmeden duran bir koşuda kesme payı ölçülmüş olurdu')
        assert 'vapor' not in set(sol['tank_phase'])

    def test_kesme_METIN_kanalindan_da_okunuyor(self, blok):
        """Alanlar programatik kapıdır; panel ``warnings`` rozetini basar.

        İki kanal birbirini kapatmaz: sayı ekrana bugün uyarı metniyle
        iniyor (ALAN kablosu arayuz borcu, TERS_MUAFIYET'te adresli).
        """
        kesme = [u for u in blok['warnings'] if 'TRUNCATED TAIL-OFF' in u]
        assert kesme, (
            'kesme uyarısı düştü: kalan pay artık ekrana hiç inmiyor '
            f'({blok["warnings"]})')
        metin = kesme[0]
        assert 'kg of oxidiser is still in the tank' in metin
        assert '%' in metin or 'of the impulse reported above' in metin


# ===========================================================================
# 3) Zarf kapısı ARTIK ATEŞLENEBİLİR — kesmenin gerekçesi
# ===========================================================================
class TestOHD2709ZarfKapisiAteslenebilir:

    def test_kapi_blokta_ALAN_olarak_var_ve_bugun_True(self, blok):
        """once.json K3: altı senaryonun altısında da zarf terk edilir."""
        assert 'vapor_tail_off_leaves_model_envelope' in blok, (
            'kuyruğun neden yürünmediğini söyleyen hüküm alanı yok')
        assert blok['vapor_tail_off_leaves_model_envelope'] is True, (
            'ölçüm zemini değişti: nominal koşuda kuyruk artık zarfı terk '
            'etmiyor — kesme gerekçesi yeniden yazılmalı')

    def test_hukum_tankin_KENDI_sabitlerinden_turetiliyor(self):
        """Tek kaynak: γ, üçlü nokta ve doygunluk hepsi tank modülünden.

        Bağıntı elle yeniden kurulup ürünün hükmüyle karşılaştırılır;
        ürün başka bir γ ya da başka bir üçlü nokta kullanıyorsa ayrışır.
        """
        tank = N2OTankBlowdown.from_oxidizer_mass(16.5, 293.15)
        Pa = 101325.0
        z = tank.vapor_tail_off_envelope(Pa)
        g = float(N2O_GAMMA_VAPOR)
        P0 = float(tank.props.psat(tank.T))
        r_dur = (Pa / P0) ** (1.0 / g)
        r_ucgen = max((N2O_T_TRIPLE / tank.T) ** (1.0 / (g - 1.0)),
                      (N2O_P_TRIPLE / P0) ** (1.0 / g))
        assert z['mass_ratio_at_flow_stop'] == pytest.approx(r_dur, rel=1e-12)
        assert z['mass_ratio_at_triple_point'] == pytest.approx(
            r_ucgen, rel=1e-12)
        assert z['leaves_envelope'] is bool(r_dur < r_ucgen)
        assert z['gamma'] == g

    def test_kapi_iki_yone_de_donebiliyor(self):
        """Ölü kapı değil: ortam basıncı yeterince yüksekse hüküm False.

        Kapı yalnız "hep True" veriyorsa yine bir uydurma sabit olurdu.
        Zarf terk edilmemesi için akışın üçlü noktadan ÖNCE durması, yani
        aşağı akış basıncının yüksek olması gerekir — bu ölçülebilir bir
        koldur ve burada ölçülür.
        """
        tank = N2OTankBlowdown.from_oxidizer_mass(16.5, 293.15)
        P0 = float(tank.props.psat(tank.T))
        assert tank.vapor_tail_off_envelope(101325.0)['leaves_envelope'] is True
        # Doygunluk basıncının %90'ına dayanan bir aşağı akış: akış hemen
        # durur, kuyruk üçlü noktaya HİÇ inmez.
        assert tank.vapor_tail_off_envelope(
            0.9 * P0)['leaves_envelope'] is False, (
            'zarf kapısı yalnız True veren ölü bir alan')

    def test_ortam_verilmezse_hukum_UYDURULMUYOR(self):
        """Fail-closed: girdisiz hüküm None kalır, False'a düşmez."""
        tank = N2OTankBlowdown.from_oxidizer_mass(16.5, 293.15)
        z = tank.vapor_tail_off_envelope(None)
        assert z['leaves_envelope'] is None
        assert z['mass_ratio_at_flow_stop'] is None
        # Eşik yine de ölçülür: girdisi olmayan taraf None, olan taraf sayı.
        assert isinstance(z['mass_ratio_at_triple_point'], float)


# ===========================================================================
# 4) Künye gerçeği söylüyor + regüleli kipte sayı uydurulmuyor
# ===========================================================================
class TestOHD2709KunyeVeFailClosed:

    def test_kunye_kesmenin_bedelini_ve_gerekcesini_soyluyor(self, blok):
        kunye = blok['tank_model_envelope_basis']
        for parca in ('residual_oxidizer_kg',
                      'residual_impulse_at_cutoff_rate_Ns',
                      'vapor_tail_off_leaves_model_envelope',
                      'vapor_phase_integrated',
                      'oxidizer_depleted', 'triple point', '240-306 K',
                      'NIST WebBook'):
            assert parca in kunye, (
                f'zarf künyesi {parca!r} demiyor — kesmenin bedeli ya da '
                'gerekçesi okunamıyor')

    def test_reguleli_kipte_pay_UYDURULMUYOR(self, taban_motor):
        """Tank yoksa artık pay yoktur: None kalır, 0 yazılmaz."""
        tb = _sessiz(TransientBallistics, taban_motor,
                     feed_mode='regulated',
                     n_steps=TANK_BLOWDOWN_N_STEPS)
        sol = _sessiz(tb.solve)
        assert sol['residual_oxidizer_kg'] is None
        assert sol['residual_impulse_at_cutoff_rate_Ns'] is None
        assert sol['residual_impulse_fraction_at_cutoff_rate'] is None
        assert sol['vapor_tail_off_leaves_model_envelope'] is None
        assert sol['vapor_phase_integrated'] is False

    def test_D27_zarf_bayragi_kanallari_AYAKTA(self, blok):
        """P13B4-04 onarımı sökülmedi (D28 onarımı onun üstüne kuruldu)."""
        assert 'vapor_model_valid' in blok
        assert 'tank_saturation_band_clamped' in blok
        assert blok['vapor_model_valid'] is True, (
            'buhar adımı integre edilmediği hâlde bayrak False — iki kanal '
            'çelişiyor')


def test_bu_dosyada_iddiasiz_test_yok():
    """ÖH OH-D23-01 kuralı: her test en az bir iddia taşır."""
    kaynak = open(os.path.abspath(__file__), encoding='utf-8').read()
    agac = ast.parse(kaynak)
    iddiasiz = []
    for dugum in ast.walk(agac):
        if not (isinstance(dugum, ast.FunctionDef)
                and dugum.name.startswith('test_')):
            continue
        if not any(isinstance(a, ast.Assert) for a in ast.walk(dugum)):
            iddiasiz.append(dugum.name)
    assert not iddiasiz, f'iddiasız test: {iddiasiz}'
