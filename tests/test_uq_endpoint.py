"""POST /api/uncertainty-analysis sözleşme testleri (v2.5.0 G3).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. Hibrit fast (N=200) GERÇEK koşu: kontrat şeması (outputs istatistik
     blokları, 21 kenarlı/20 kutulu histogram, |rho| sıralı sensitivity,
     mean_shift_percent), cd_injector'ın dağılımdan çıkarıldığı (sahte 0
     duyarlılık YOK), fiziksel akıl sağlığı bantları.
  2. Seed determinizmi (katı fast, hızlı): aynı seed -> timing dışında birebir
     aynı gövde; farklı seed -> farklı istatistik.
  3. 400 yolları: bilinmeyen motor_type / level, bozuk seed / n_samples,
     bozuk distribution_overrides.
  4. Katı / sıvı fast duman testleri (kontrat çıktı anahtar kümeleri; sıvı
     koşusu AĞSIZ — fetch yaması ile).
  5. distribution_overrides: disabled parametre sensitivity'den kaybolur.
  5b. Dejenere dağılım reddi (t19 deseninin uq_adapters ucundaki ikizi):
     katı max_pressure girdinin donmuş yankısı olamaz, sıvı kolunda Pc/MR/eta
     saçılımı çıktılara geçer, F029 nominal sabitlemesi kaymayla GÖRÜNÜR
     (ÖH FAZ B-1 adım #3 — defter P14M2-13 / P5B2-06).
  6. high_fidelity -> 202 queued + GET /api/jobs/<id> yoklaması done'a ulaşır;
     job.result kontrat 'ok' gövdesidir.
  7. Örnek #0 tutarlılık kırılması -> 500 + 'diverged' mesajı (sessiz düşme
     yok — spec 7.3).
"""

import copy
import time

import pytest

HYBRID_INPUTS = {
    'thrust': 1000.0,
    'burn_time': 10.0,
    'of_ratio': 6.0,
    'chamber_pressure': 30.0,
    'fuel_type': 'htpb',
}
SOLID_INPUTS = {
    'grain_type': 'bates',
    'propellant_type': 'apcp',
    'chamber_diameter': 100,
    'grain_length': 500,
    'core_diameter': 30,
    'chamber_pressure': 40,
    'burn_rate_a': 0.005,
    'burn_rate_n': 0.35,
}
LIQUID_INPUTS = {
    'thrust': 10000.0,
    'chamber_pressure': 100.0,
    'mixture_ratio': 2.5,
    'fuel_type': 'rp1',
    'oxidizer_type': 'lox',
}

HYBRID_OUTPUT_KEYS = {'isp', 'thrust', 'chamber_pressure', 'c_star',
                      'total_impulse', 'regression_rate_avg'}
SOLID_OUTPUT_KEYS = {'isp', 'c_star', 'max_pressure', 'total_impulse'}
LIQUID_OUTPUT_KEYS = {'isp', 'thrust', 'c_star', 'mdot_total'}

STAT_FIELDS = ('nominal', 'mean', 'std', 'cv', 'p5', 'p25', 'p50', 'p75',
               'p95', 'histogram')

# Hibrit varsayılan dağılım kümesi (cd_injector ÇIKARILMIŞ hali)
# ÖH D15 / P5B2-07 (kulvar yapisal-sistem, a3) — BEKÇİ ÇEVRİLDİ.
# Bu küme ``fuel_density``i duyarlılık tablosuna KİLİTLİYORDU. ÖLÇÜLDÜ
# (docs/scofield/raw/OH/D15/yapisal-sistem/a3/once.json): parametre +3σ'da
# (çarpan 1,06) altı sözleşme çıktısının ALTISINI DA BİT-AYNI bırakıyor,
# yani satır ρ = 0 ile çiziliyordu. Modülün kendi dürüstlük kuralı
# (``uq_adapters.UNMAPPED_PARAMS`` yorumu) "sensitivity'de sahte 0
# göstermek yerine hiç raporlanmaz" diyor; kural
# ``ZERO_CONTRACT_INFLUENCE`` dalıyla tamamlandı ve parametre dağılımdan
# düşürüldü. Kümedeki iddia DEĞİŞMEDİ (uç hangi parametreleri raporluyorsa
# tam olarak onları raporlamalı); yalnız beklenen küme ölçülen gerçeğe
# çekildi. Ölçümün kendisi ``tests/test_d15_yapisal_sistem_a3.py``
# içinde İKİ YÖNLÜ bekçidir: katkı doğarsa o test kırmızı verir.
#
# ÖH D26 fix-25a — ``fuel_density`` KÜMEYE GERİ GİRDİ ve yukarıdaki ölçüm
# bayatladı. O iki yönlü bekçi tam da öngördüğü işi yaptı: parametre artık
# sözleşme çıktılarını oynatıyor (taban 7751531, ±3σ: isp bağıl 2,240e-04 /
# 2,100e-04; regression_rate_avg 1,785e-05 / 1,674e-05 — platform gürültü
# tabanının 1e-12 sekiz mertebe üstünde). Kanal ``a109e4a`` (ÖH D22 hibrit
# a1, OH-D21-02/OH-D21-03) ile açıldı: ρ_f tane/kamara boyutlandırmasını,
# o da GERÇEKLEŞEN L*'ı (3,5438 -> 3,6037 / 3,3282 m), o da kinetik verimi
# ve CF/Isp'i oynatıyor. ``ZERO_CONTRACT_INFLUENCE`` dalının ölçüm dayanağı
# kalmadığından parametre dağılıma döndü; satır sahte 0 DEĞİL (seed 42,
# fast: isp ρ = -0,0562; regression_rate_avg ρ = +0,1335, üçüncü sırada).
# İddia yine DEĞİŞMEDİ (uç hangi parametreleri raporluyorsa tam olarak
# onları raporlamalı); yalnız beklenen küme ölçülen gerçeğe çekildi.
HYBRID_PARAMS = {'regression_lambda', 'regression_n_delta', 'eta_c_star',
                 'chamber_pressure', 'fuel_density'}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module', autouse=True)
def no_liquid_network():
    """Sıvı fabrika kurulumundaki tek seferlik veri çekimini ağsızlaştırır.

    Yamalanan metod hiçbir şey doldurmaz; property savunmacı dalı boş sözlüğe
    düşer ve motor kendi referans yoğunluklarını kullanır (record_adapters
    AĞSIZ koşu kalıbının aynısı). Testler ağa çıkmaz.
    """
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    original = LiquidRocketEngine._fetch_web_propellant_data
    LiquidRocketEngine._fetch_web_propellant_data = lambda self: None
    yield
    LiquidRocketEngine._fetch_web_propellant_data = original


def _post_uq(client, **payload):
    return client.post('/api/uncertainty-analysis', json=payload)


def _strip_timing(body):
    body = copy.deepcopy(body)
    body.pop('timing_s', None)
    return body


# ---------------------------------------------------------------------------
# 1) Hibrit fast N=200 gerçek koşu — kontrat şeması
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def hybrid_fast(client):
    resp = _post_uq(client, motor_type='hybrid', level='fast', seed=42,
                    inputs=HYBRID_INPUTS)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


class TestHybridFastContract:
    def test_top_level_fields(self, hybrid_fast):
        body = hybrid_fast
        assert body['status'] == 'ok'
        assert body['motor_type'] == 'hybrid'
        assert body['level'] == 'fast'
        assert body['n_samples'] == 200  # LEVEL_BUDGETS['fast']
        assert body['seed'] == 42
        assert isinstance(body['failed_samples'], int)
        assert body['failed_samples'] <= 10, body['failed_samples']
        assert body['timing_s'] > 0

    def test_output_blocks(self, hybrid_fast):
        outputs = hybrid_fast['outputs']
        assert set(outputs) == HYBRID_OUTPUT_KEYS
        kept = hybrid_fast['n_samples'] - hybrid_fast['failed_samples']
        for key, block in outputs.items():
            for field in STAT_FIELDS:
                assert field in block, (key, field)
            hist = block['histogram']
            assert len(hist['edges']) == 21, key
            assert len(hist['counts']) == 20, key
            assert sum(hist['counts']) == kept, key
            assert block['p5'] <= block['p25'] <= block['p50'] \
                <= block['p75'] <= block['p95'], key

    def test_physical_sanity(self, hybrid_fast):
        outputs = hybrid_fast['outputs']
        assert 150 < outputs['isp']['nominal'] < 350
        assert 1200 < outputs['c_star']['nominal'] < 1900
        # F girdi olduğundan itki dağılmaz (F-sabit sözleşmesi)
        assert outputs['thrust']['std'] == pytest.approx(0.0, abs=1e-9)
        # eta_c* ve Pc dağıldığı için Isp dağılır
        assert outputs['isp']['std'] > 0

    def test_sensitivity_contract(self, hybrid_fast):
        sens = hybrid_fast['sensitivity']
        assert set(sens) == HYBRID_OUTPUT_KEYS
        for key, rows in sens.items():
            params = [row['param'] for row in rows]
            # cd_injector haritalanamaz, fuel_density sözleşme çıktılarını
            # hiç oynatmıyor -> ikisi de dağılımdan ÇIKARILDI (sahte 0 yok)
            assert set(params) == HYBRID_PARAMS, key
            rhos = [row['rho'] for row in rows]
            assert all(-1.0 <= r <= 1.0 for r in rhos), key
            mags = [abs(r) for r in rhos]
            assert mags == sorted(mags, reverse=True), key
        # Isp'yi hibritte eta_c* domine eder (fiziksel beklenti)
        assert sens['isp'][0]['param'] == 'eta_c_star'
        assert sens['isp'][0]['rho'] > 0.8

    def test_mean_shift_percent(self, hybrid_fast):
        """Kayma = eta_c* sabitleme terimi + (çok küçük) Jensen artığı.

        v2.6.2 fizik denetimi F029, eta_c_star'ın UQ NOMİNALİNİ 1.0'a
        (deterministik /calculate yolunun teorik c*'ı) sabitledi; dağılımın
        kendisi 0.93 ortalamada BIRAKILDI. Tasarım gereği MC ortalaması artık
        nominalin ~%7 altındadır ve bu fark sessizce nominale gömülmek yerine
        mean_shift_percent'te GÖRÜNÜR. Testin eski hali (|kayma| < %5) kaymanın
        tek bileşeninin doğrusalsızlık olduğu döneme aitti; sözleşme aşağıda
        gevşetilmedi, İKİ BİLEŞENE AYRIŞTIRILDI (artık için sınır %5 değil
        0.5 PUAN — 10 kat DAHA SIKI).

        El hesabı — eta ~ truncnorm(ortalama 0.93, sigma 0.03) [0.80, 1.00]:
            a = (0.80−0.93)/0.03 = −4.3333,  b = (1.00−0.93)/0.03 = +2.3333
            E[eta] = 0.93 + 0.03·(φ(a)−φ(b))/(Φ(b)−Φ(a))
                   = 0.93 + 0.03·(0.0000294−0.026215)/0.990178 = 0.929207
            beklenen kayma = (0.929207/1.0 − 1)·100 = −7.079 %
        Isp ∝ c*_teslim = eta·c*_teorik olduğu için terim isp ve c_star'a
        birebir geçer (Sutton & Biblarz 9. baskı Denk. 3-31).

        ÖLÇÜLDÜ (seed=42, N=200): isp kayması −7.076465 %; LHS örnek
        ortalaması E_örnek[eta] = 0.929258 → eta terimi −7.074246 %; artık
        −0.0022 puan. Bağımsız teyit: eta_c_star dağılımdan ÇIKARILDIĞINDA
        (distribution_overrides {'eta_c_star': None}) saf Jensen boşluğu
        isp için −0.0031 %, c_star için −0.0004 %.
        """
        from scipy.stats import truncnorm

        from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS

        shift = hybrid_fast['mean_shift_percent']
        assert set(shift) == HYBRID_OUTPUT_KEYS

        eta = DEFAULT_UQ_MODELS['hybrid']['eta_c_star']
        assert eta.nominal_override == 1.0  # F029 sabitlemesi yürürlükte
        a = (eta.low - eta.mean) / eta.sigma
        b = (eta.high - eta.mean) / eta.sigma
        eta_mean = float(truncnorm.mean(a, b, loc=eta.mean, scale=eta.sigma))
        expected = (eta_mean / eta.nominal_override - 1.0) * 100.0
        assert expected == pytest.approx(-7.079, abs=0.005)  # el hesabı çapası

        # c* ile doğrusal çıktılar sabitleme terimini TAŞIR; geriye kalan
        # artık gerçek Jensen boşluğudur ve 0.5 puanın altında kalmalıdır.
        for key in ('isp', 'c_star'):
            assert shift[key] == pytest.approx(expected, abs=0.5), key
        # eta'dan etkilenmeyen çıktıda kayma zaten saf Jensen boşluğudur.
        assert abs(shift['regression_rate_avg']) < 5.0
        # F girdi olduğundan itki/toplam impuls dağılmaz -> kayma tam sıfır.
        assert shift['thrust'] == pytest.approx(0.0, abs=1e-9)
        assert shift['total_impulse'] == pytest.approx(0.0, abs=1e-9)

        # Nominal ASLA MC ortalamasıyla değiştirilmez: raporlanan kayma her
        # blokta (mean, nominal) çiftinden birebir türetilebilmeli.
        for key, block in hybrid_fast['outputs'].items():
            assert shift[key] == pytest.approx(
                (block['mean'] - block['nominal']) / abs(block['nominal'])
                * 100.0, rel=1e-9), key


# ---------------------------------------------------------------------------
# 2) Seed determinizmi (katı — hızlı gerçek koşu)
# ---------------------------------------------------------------------------

class TestSeedDeterminism:
    def test_same_seed_identical_body(self, client):
        kwargs = dict(motor_type='solid', level='fast', seed=42,
                      inputs=SOLID_INPUTS, n_samples=60)
        b1 = _post_uq(client, **kwargs).get_json()
        b2 = _post_uq(client, **kwargs).get_json()
        assert b1['status'] == b2['status'] == 'ok'
        assert _strip_timing(b1) == _strip_timing(b2)

    def test_different_seed_differs(self, client):
        base = dict(motor_type='solid', level='fast', inputs=SOLID_INPUTS,
                    n_samples=60)
        b1 = _post_uq(client, seed=42, **base).get_json()
        b2 = _post_uq(client, seed=43, **base).get_json()
        assert b1['outputs']['isp']['mean'] != b2['outputs']['isp']['mean']


# ---------------------------------------------------------------------------
# 3) 400 yolları
# ---------------------------------------------------------------------------

class TestBadRequests:
    def test_unknown_motor_type(self, client):
        resp = _post_uq(client, motor_type='ion', level='fast', inputs={})
        assert resp.status_code == 400
        assert 'motor_type' in resp.get_json()['error']

    def test_unknown_level(self, client):
        resp = _post_uq(client, motor_type='solid', level='ultra', inputs={})
        assert resp.status_code == 400
        assert 'level' in resp.get_json()['error']

    def test_bad_seed(self, client):
        resp = _post_uq(client, motor_type='solid', level='fast',
                        seed='kirk-iki', inputs=SOLID_INPUTS)
        assert resp.status_code == 400

    def test_bad_n_samples(self, client):
        resp = _post_uq(client, motor_type='solid', level='fast',
                        n_samples='hepsi', inputs=SOLID_INPUTS)
        assert resp.status_code == 400

    def test_bad_override_field(self, client):
        resp = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS,
                        distribution_overrides={
                            'burn_rate_a': {'stddev': 0.1}})
        assert resp.status_code == 400
        assert 'unknown field' in resp.get_json()['error']

    def test_all_disabled_rejected(self, client):
        overrides = {name: {'disabled': True}
                     for name in ('burn_rate_a', 'burn_rate_n_delta',
                                  'density', 'c_star')}
        resp = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS,
                        distribution_overrides=overrides)
        assert resp.status_code == 400

    def test_inputs_must_be_object(self, client):
        resp = _post_uq(client, motor_type='solid', level='fast',
                        inputs=[1, 2, 3])
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4) Katı / sıvı fast duman testleri
# ---------------------------------------------------------------------------

class TestSolidLiquidSmoke:
    def test_solid_fast(self, client):
        body = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS, n_samples=60).get_json()
        assert body['status'] == 'ok'
        assert set(body['outputs']) == SOLID_OUTPUT_KEYS
        assert body['n_samples'] == 60
        assert 150 < body['outputs']['isp']['nominal'] < 320
        assert body['outputs']['max_pressure']['nominal'] > 0

    def test_liquid_fast(self, client):
        body = _post_uq(client, motor_type='liquid', level='fast',
                        inputs=LIQUID_INPUTS, n_samples=60).get_json()
        assert body['status'] == 'ok'
        assert set(body['outputs']) == LIQUID_OUTPUT_KEYS
        # F sabit sözleşmesi: itki dağılmaz, Isp eta_c* ile dağılır
        assert body['outputs']['thrust']['std'] == pytest.approx(0.0,
                                                                 abs=1e-9)
        assert body['outputs']['isp']['std'] > 0
        assert body['outputs']['mdot_total']['nominal'] > 0

    def test_disabled_override_removes_param(self, client):
        body = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS, n_samples=60,
                        distribution_overrides={
                            'burn_rate_a': {'disabled': True}}).get_json()
        assert body['status'] == 'ok'
        for rows in body['sensitivity'].values():
            assert all(row['param'] != 'burn_rate_a' for row in rows)

    def test_std_override_accepted(self, client):
        body = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS, n_samples=60,
                        distribution_overrides={
                            'burn_rate_a': {'std': 0.06, 'low': 0.76,
                                            'high': 1.24}}).get_json()
        assert body['status'] == 'ok'
        labels = {entry['name']: entry for entry in body['inputs_used']}
        assert labels['burn_rate_a']['sigma'] == pytest.approx(0.06)


# ---------------------------------------------------------------------------
# 5b) Dejenere dağılım reddi — t19 deseninin uq_adapters UCUNDAKİ ikizi
#     (ÖH FAZ B-1 adım #3; defter P14M2-13 + P5B2-06)
# ---------------------------------------------------------------------------

#: Sabit bir çıktının std'si bu uçta 0,0 değil MAKİNE GÜRÜLTÜSÜ çıkıyor
#: (ölçüldü, katı max_pressure, seed=42/N=60: std = 3,18e-15 bar,
#: cv = 7,94e-15 %, p5/p95 = 39,99999999999999 / 40,00000000000001).
#: Bu yüzden t19'un ``std > 0`` ve ``p95 > nominal > p5`` yan tümceleri bu
#: uca BİREBİR taşındığında GÜRÜLTÜYLE geçer; taşıma bu iki tabana çapalanır.
#: 1e-6 bar = 0,1 Pa — hiçbir gerçek yakıt partisi saçılımı bunun altında
#: olamaz, hiçbir yuvarlama artığı bunun üstüne çıkamaz.
GURULTU_TABANI_BAR = 1e-6
#: Aynı tabanın BİRİMSİZ (nominale göre bağıl) hali — basınç dışındaki
#: çıktılarda (isp [s], c_star [m/s], total_impulse [N·s], mdot [kg/s])
#: kullanılır. Birim körlüğüne düşmemek için bar tabanından AYRI tutulur.
GURULTU_TABANI_BAGIL = 1e-6
#: [p5, p95] açıklığının anlamlılık tabanı [bar] (ölçülen dejenere açıklık
#: 2,1e-14 bar; onarımdan sonra beklenen ~%5 CV'de ≈ 1,3 bar).
BANT_TABANI_BAR = 0.1


@pytest.fixture(scope='module')
def kati_dagilim(client):
    """Katı UQ ucunun TEK koşusu (seed=42, N=60).

    Dağılım bekçileri bu koşuyu paylaşır (Monte Carlo pahalı).
    """
    resp = _post_uq(client, motor_type='solid', level='fast', seed=42,
                    inputs=SOLID_INPUTS, n_samples=60)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


@pytest.fixture(scope='module')
def sivi_dagilim(client):
    """Sıvı UQ ucunun TEK koşusu (seed=42, N=60).

    AĞSIZ: ``no_liquid_network`` fikstürü fabrika kurulumundaki tek seferlik
    veri çekimini yamalar.
    """
    resp = _post_uq(client, motor_type='liquid', level='fast', seed=42,
                    inputs=LIQUID_INPUTS, n_samples=60)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


class TestDejenereDagilimReddi:
    """t19'un dejenere-dağılım reddi, ``uq_adapters`` ucuna taşınmış hali.

    NEDEN — ölçülmüş kusur (defter P14M2-13, P5B2-06)
    -------------------------------------------------
    Katı motorun tepe basıncını üreten İKİ yol var ve doğru bekçi yalnız
    birine yazılmıştı:

      * ``SolidRocketEngine.run_monte_carlo`` — t19 tarafından korunuyor
        (``tests/test_faz6_f8_motor.py:142-156``, dejenere dağılım reddi:
        ``std > 0`` · ``cv > 1`` · ``p95 > nominal > p5``). Bu desen P14
        savcısı tarafından SAĞLIKLI ilan edildi; buraya KOPYALANDI,
        kaynağına dokunulmadı.
      * ``hrma/analysis/uq_adapters.make_solid_factory`` — ``/api/uncertainty
        -analysis`` ucunun kullandığı İKİZ üretici. Bekçisiz.

    P14 mutasyonu (``'max_pressure': 1.0 if pressure_curve else None``,
    uq_adapters.py:305) 6 dosya / 140 testte SIFIR kırmızı üretti: uçtaki tek
    iddia ``max_pressure['nominal'] > 0`` idi ve 1,0 > 0 doğrudur.

    ÖLÇÜLEN (bu bekçiler yazılırken, seed=42 / N=60, katı varsayılan giriş)
    ---------------------------------------------------------------------
        max_pressure : nominal 40,000000 bar   mean 40,000000 bar
                       std 3,18e-15 bar        cv 7,94e-15 %
                       p5 39,99999999999999    p95 40,00000000000001
        c_star       : cv 0,991 %   (dağılıyor)
        isp          : cv 0,994 %   (dağılıyor)
        total_impulse: cv 1,478 %   (dağılıyor)

    Yani uçtaki tepe basıncı, GİRDİNİN donmuş yankısıdır — t19'un kapattığı
    kusurun ta kendisi ikizde yaşıyor. Kök sebep okunarak doğrulandı:
    ``run_monte_carlo`` her örnek motorunda
    ``pin_throat_area(nom_throat_area)`` çağırıyor
    (``solid_rocket_engine.py:5579``), ``uq_adapters`` çağırmıyor — boğaz her
    örnekte yeniden boyutlandığı için denge Pc tam girilen değere geri
    kilitleniyor.

    KAPSAM — sıvı kolu
    ------------------
    Sıvı kolu tepe basıncı YAYIMLAMIYOR (ölçüldü: çıktı kümesi
    ``isp / thrust / c_star / mdot_total``). Bu yüzden aynı desen sıvıda
    "basınç saçılımı" olarak değil, Pc/MR/eta saçılımını TAŞIYAN çıktılar
    üzerinde kurulur; basınç çıktısı eklenirse bekçinin genişletilmesi
    ``test_sivi_kolu_tepe_basinc_yayimlamiyor`` tarafından ŞART KOŞULUR.
    t19'un ``p95 > nominal > p5`` yan tümcesi sıvıda UYGULANAMAZ ve sebebi
    ölçülmüştür (F029 nominal sabitlemesi — aşağıdaki testin gövdesi).
    """

    # -- Katı ------------------------------------------------------------
    def test_kati_max_pressure_nominali_girilen_pc_ye_capali(self,
                                                             kati_dagilim):
        """``> 0`` bir çapa DEĞİLDİR: nominal tepe basıncı girdiye bağlanır.

        Tasarım noktasında katı motorun tepe basıncı girilen oda basıncıdır
        (t19'un ``test_t19_design_path_is_untouched_by_the_fix`` iddiasının
        uçtaki eşi). Ölçüldü (seed=42, N=60): nominal = 40,000000 bar =
        ``SOLID_INPUTS['chamber_pressure']``; p5 = p95 = 40,000000 bar.

        Bu iddia BUGÜN yeşildir ve P14 mutasyonunu (sabit 1,0 bar) tek başına
        kırmızıya çevirir — dağılımın dejenere olup olmadığından bağımsız
        olarak. Bandlar (%50 / %200) onarım sonrası saçılıma yer bırakacak
        kadar geniş, birim hatasına (bar -> Pa, 4,0e6) kapalı olacak kadar dar.
        """
        blok = kati_dagilim['outputs']['max_pressure']
        pc_girdi = float(SOLID_INPUTS['chamber_pressure'])
        assert blok['nominal'] == pytest.approx(pc_girdi, rel=1e-6), blok
        assert blok['mean'] == pytest.approx(pc_girdi, rel=0.25), blok
        assert blok['p50'] == pytest.approx(pc_girdi, rel=0.25), blok
        assert blok['p5'] > 0.5 * pc_girdi, blok
        assert blok['p95'] < 2.0 * pc_girdi, blok

    def test_kati_max_pressure_gercek_sacilima_sahip(self, kati_dagilim):
        """Katı tepe basıncı yakıt partisiyle GERÇEKTEN oynamalı (t19 deseni).

        ONARILDI (ÖH D26 / P5B2-06): BORÇ İMİ KALDIRILDI. Kök,
        ``uq_adapters.make_solid_factory``ın ``run_monte_carlo``
        kalıbındaki ``pin_throat_area`` adımını atlamasıydı: boğaz her
        örnekte bozulmuş partiye göre yeniden boyutlandırılınca denge
        basıncı tasarım noktasına geri kilitleniyordu. Fabrika artık
        nominal boğaz alanını ``probe._design_throat_area()`` ile bir kez
        çözüp her örneğe sabitliyor (donanım tektir).

        Üç yan tümce ``test_t19_monte_carlo_peak_pressure_has_real_scatter``
        gövdesinden birebir taşındı; tek uyarlama alan adı: uç sözleşmesinde
        ``cv_percent`` -> ``cv`` (ikisi de YÜZDE — app.py:11515'in künyesi).

        Taşınırken ölçülen DELİK — kopyalanan desen bu uçta iki yerden
        gürültüyle geçiyor (yukarıdaki ``GURULTU_TABANI_BAR`` künyesi):
        ``std > 0`` 3,18e-15 ile, ``p95 > nominal > p5`` 1e-14'lük yuvarlama
        artığıyla. Bu yüzden her iki yan tümceye ÖLÇÜLMÜŞ bir taban eklendi;
        t19'un kendi dosyasında böyle bir taban gerekmiyor (orada dejenere
        dağılım tam eşitlik veriyordu).
        """
        blok = kati_dagilim['outputs']['max_pressure']
        # (1) t19: sıfır sapma yasak — + bu uçta gürültü tabanı
        assert blok['std'] > 0.0, 'tepe basıncı hâlâ sıfır sapmalı'
        assert blok['std'] > GURULTU_TABANI_BAR, (
            'std makine gürültüsü mertebesinde (%r bar): dağılım dejenere'
            % blok['std'])
        # (2) t19: basınç, itkiyle karşılaştırılabilir bir saçılıma sahip
        #     olmalı. Bu uçta ISIRAN yan tümce budur (ölçüldü 7,94e-15 %).
        assert blok['cv'] > 1.0, blok
        # (3) t19: nominal dağılımın İÇİNDE olmalı — + açıklık tabanı
        assert blok['p95'] > blok['p5'], blok
        assert blok['p95'] > blok['nominal'] > blok['p5'], blok
        assert blok['p95'] - blok['p5'] > BANT_TABANI_BAR, (
            '[p5,p95] açıklığı %r bar — yuvarlama artığı mertebesinde'
            % (blok['p95'] - blok['p5']))

    def test_kati_dagilan_ciktilar_dejenere_degil(self, kati_dagilim):
        """Aynı koşuda DAĞILAN çıktılar — bekçinin anlamlı olduğunun kanıtı.

        Bu olmasaydı 'max_pressure sabit' hükmü koşunun tamamının ölü
        olmasıyla açıklanabilirdi. Ölçüldü (seed=42, N=60): c_star 0,991 %,
        isp 0,994 %, total_impulse 1,478 % CV — yani örnekleyici çalışıyor,
        sabit olan YALNIZ tepe basıncı.
        """
        outputs = kati_dagilim['outputs']
        assert kati_dagilim['failed_samples'] == 0, kati_dagilim
        for ad in ('isp', 'c_star', 'total_impulse'):
            blok = outputs[ad]
            assert blok['std'] > GURULTU_TABANI_BAGIL * abs(blok['nominal']), (
                ad, blok['std'])
            assert blok['cv'] > 0.5, (ad, blok['cv'])
            assert blok['p95'] > blok['p5'], ad

    # -- Sıvı ------------------------------------------------------------
    def test_sivi_kolu_tepe_basinc_yayimlamiyor(self, sivi_dagilim):
        """Sıvı çıktı kümesinde basınç YOK — bilinçli kilit + güncelleme emri.

        Ölçüldü: sıvı kolu ``isp / thrust / c_star / mdot_total`` yayımlıyor,
        basınç adı taşıyan çıktı yok. Bu iddia bugünkü GERÇEĞİ kilitler; kilit
        kırıldığı gün (yani sıvı kola bir basınç çıktısı eklendiği gün) hata
        mesajı ne yapılacağını söyler — katı koldaki dejenere-dağılım bekçisi
        o çıktı için de yazılmalıdır. ('Bilinçli-kilitleyen + güncelleme
        protokolü' deseni: test_field_wiring_layer_b.py:851.)
        """
        basincli = sorted(ad for ad in sivi_dagilim['outputs']
                          if 'pressure' in ad or 'basinc' in ad)
        assert basincli == [], (
            'sıvı kolu artık basınç yayımlıyor (%r): katı koldaki '
            'dejenere-dağılım bekçisinin (t19 deseni: std/cv/bant) ikizi bu '
            'çıktı için de YAZILMALI — ÖH defter P14M2-13' % basincli)

    def test_sivi_dagilimi_dejenere_degil(self, sivi_dagilim):
        """Sıvıda Pc/MR/eta saçılımı çıktılara GERÇEKTEN geçiyor mu.

        Ölçüldü (seed=42, N=60, ağsız): isp CV 2,035 %, c_star CV 1,992 %,
        mdot_total CV 2,052 %; itki tam sıfır sapmalı (F sabit sözleşmesi).
        Dağılan girdiler: chamber_pressure ±%2, mixture_ratio ±%2,
        eta_c_star truncnorm(0,96; 0,02) [0,88 , 1,00].
        """
        outputs = sivi_dagilim['outputs']
        assert sivi_dagilim['failed_samples'] == 0, sivi_dagilim
        for ad in ('isp', 'c_star', 'mdot_total'):
            blok = outputs[ad]
            assert blok['std'] > GURULTU_TABANI_BAGIL * abs(blok['nominal']), (
                ad, blok['std'])
            assert blok['cv'] > 1.0, (ad, blok['cv'])
            assert blok['p95'] - blok['p5'] > 0.01 * abs(blok['nominal']), ad
        # Ters yön: F girdi olduğu için itki DAĞILMAMALI (t19'un 'hangi
        # büyüklük donanım' beyanının sıvıdaki karşılığı).
        assert outputs['thrust']['std'] == pytest.approx(0.0, abs=1e-9)

    def test_sivi_nominali_dagilimin_kenarindadir_ve_kayma_raporlanir(
            self, sivi_dagilim):
        """t19'un ``p95 > nominal > p5`` yan tümcesi sıvıda neden UYGULANMAZ.

        F029 sabitlemesi: ``eta_c_star`` UQ nominali 1,0'a (deterministik
        ``/calculate_liquid`` yolunun teorik c*'ı) sabitlenmiş, dağılımın
        kendisi 0,96 ortalamada bırakılmıştır. Dolayısıyla nominal, dağılımın
        İÇİNDE değil KENARINDADIR ve fark sessizce gömülmez, ``mean_shift_
        percent``'te görünür. Ölçüldü (seed=42, N=60):
            isp        nominal 298,3708  p50 286,2420  kayma −4,1304 %
            c_star     nominal 1808,8847 p50 1735,4022 kayma −4,1291 %
            mdot_total nominal   3,4176  p50   3,5624  kayma +4,3519 %
        El hesabı çapası — eta ~ truncnorm(0,96; 0,02) [0,88 , 1,00]:
            a = −4,0 ; b = +2,0 ; E[eta] = 0,958897746
            beklenen kayma = (0,958898/1,0 − 1)·100 = −4,110225 %
            mdot = mdot_ref/eta olduğu için E[1/eta] = 1,043268 → +4,326814 %
        Ölçümle el hesabı arasındaki 0,02-0,03 puanlık fark LHS örnek
        ortalamasının artığıdır.

        Bu iddia dağılımın DÜZLEŞTİRİLMESİNİ de yakalar: bütün örnekler
        sabitlenirse kayma 0'a düşer ve bant tümcesi kırmızıya döner.
        """
        from scipy.stats import truncnorm

        from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS

        eta = DEFAULT_UQ_MODELS['liquid']['eta_c_star']
        assert eta.nominal_override == 1.0  # F029 sabitlemesi yürürlükte
        a = (eta.low - eta.mean) / eta.sigma
        b = (eta.high - eta.mean) / eta.sigma
        eta_mean = float(truncnorm.mean(a, b, loc=eta.mean, scale=eta.sigma))
        beklenen = (eta_mean / eta.nominal_override - 1.0) * 100.0
        assert beklenen == pytest.approx(-4.110, abs=0.005)  # el hesabı çapası

        kayma = sivi_dagilim['mean_shift_percent']
        outputs = sivi_dagilim['outputs']
        for ad in ('isp', 'c_star'):
            assert kayma[ad] == pytest.approx(beklenen, abs=0.5), (ad,
                                                                   kayma[ad])
            assert outputs[ad]['nominal'] > outputs[ad]['p50'], ad
        # mdot = mdot_ref/eta: Jensen ters yönde (E[1/eta] > 1/E[eta])
        assert kayma['mdot_total'] == pytest.approx(4.327, abs=0.5), kayma
        assert outputs['mdot_total']['nominal'] < outputs['mdot_total']['p50']
        assert kayma['thrust'] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 6) high_fidelity -> job_runner kuyruğu + yoklama
# ---------------------------------------------------------------------------

class TestHighFidelityJob:
    def test_queued_then_polled_to_done(self, client):
        resp = _post_uq(client, motor_type='solid', level='high_fidelity',
                        inputs=SOLID_INPUTS, n_samples=60)
        assert resp.status_code == 202
        body = resp.get_json()
        assert body['status'] == 'queued'
        assert body['job_id']
        assert body['poll_url'] == f"/api/jobs/{body['job_id']}"

        deadline = time.time() + 90.0
        job = None
        while time.time() < deadline:
            poll = client.get(body['poll_url'])
            assert poll.status_code == 200
            job = poll.get_json()['job']
            if job['state'] in ('done', 'error'):
                break
            time.sleep(0.25)
        assert job is not None and job['state'] == 'done', job
        result = job['result']
        assert result['status'] == 'ok'
        assert result['motor_type'] == 'solid'
        assert result['level'] == 'high_fidelity'
        assert result['n_samples'] == 60
        assert set(result['outputs']) == SOLID_OUTPUT_KEYS


# ---------------------------------------------------------------------------
# 7) Örnek #0 tutarlılık kırılması -> 500 (sessiz düşme yok)
# ---------------------------------------------------------------------------

class TestConsistencyGuard:
    def test_sample0_divergence_is_500(self, client, monkeypatch):
        from hrma.analysis import uq_adapters

        calls = {'n': 0}

        def fake_make_factory(motor_type, inputs, track_performance=False):
            def factory(sample):
                calls['n'] += 1
                return {'isp': 200.0 + calls['n']}  # deterministik DEĞİL
            return factory

        monkeypatch.setattr(uq_adapters, 'make_factory', fake_make_factory)
        resp = _post_uq(client, motor_type='solid', level='fast',
                        inputs=SOLID_INPUTS, n_samples=60)
        assert resp.status_code == 500
        body = resp.get_json()
        assert body['status'] == 'error'
        assert 'diverged' in body['error']


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
