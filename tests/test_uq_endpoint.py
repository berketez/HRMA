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
HYBRID_PARAMS = {'regression_lambda', 'regression_n_delta', 'eta_c_star',
                 'fuel_density', 'chamber_pressure'}


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
            # cd_injector haritalanamaz -> dağılımdan ÇIKARILDI (sahte 0 yok)
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
