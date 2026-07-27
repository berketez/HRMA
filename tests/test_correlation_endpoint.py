"""GET/POST /api/correlation-report sözleşme testleri (v2.5.0 G3).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. İlk koşu (POST refresh -> önbellek atlanır): kontrat şeması — db_hash,
     record_counts, katmanlı hücreler, skipped_summary, markdown.
  2. Önbellek: aynı DB ile ikinci GET cached=true döner ve içerik birebir
     aynıdır (yalnız 'cached' bayrağı değişir).
  3. POST {refresh:true} önbelleği yok sayıp yeniden koşar (cached=false).
  4. db_hash bağımsız doğrulama: experiment_db içerik hash'i ile birebir.
  5. Markdown emoji'siz ve İngilizce başlıklı.
  6. record_type düzeltme kilidi: Whitmore fit/istatistik kayıtları ile Nakka
     a-n fitleri artık 'not_supported' katmanında raporlanır (G3 davranış
     değişikliği — sessiz insufficient_inputs değil, dürüst v1-kapsam-dışı).

Not: Tam korelasyon koşusu Cantera denge çözümleri nedeniyle ~15-25 s sürer;
bu modül bilinçli olarak İKİ gerçek koşu içerir (ilk koşu + refresh).
"""

import pytest

CELL_FIELDS = ('motor_type', 'quantity', 'layer', 'n', 'bias_percent',
               'rms_percent', 'median_ape_percent', 'mape_percent',
               'worst_test_id')
VALID_LAYERS = {'main', 'low_confidence', 'anomaly'}

RETYPED_NOT_SUPPORTED = {
    'hyb-whitmore2020-abs-gox-regfit',
    'hyb-whitmore2020-abs-gox-stats13',
    'hyb-whitmore2020-abs-nytrox87-regfit',
    'hyb-whitmore2020-abs-nytrox87-stats19',
    'hyb-whitmore2020-multi-regfit-literature',
    'sol-nakka1999-kndx-anfit',
    'sol-nakka1999-knsb-anfit',
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def fresh_report(client):
    """Önbellekten bağımsız GERÇEK koşu (refresh=true)."""
    resp = client.post('/api/correlation-report', json={'refresh': True})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['cached'] is False
    return body


class TestFirstRunSchema:
    def test_top_level(self, fresh_report):
        body = fresh_report
        assert body['status'] == 'ok'
        assert isinstance(body['db_hash'], str) and len(body['db_hash']) == 64
        assert body['generated_s'] > 0

    def test_db_hash_matches_experiment_db(self, fresh_report):
        from hrma.validation.correlation_runner import db_content_hash
        from hrma.validation.experiment_db import (load_records,
                                                   records_for_statistics)
        records = records_for_statistics(load_records())
        assert fresh_report['db_hash'] == db_content_hash(records)
        assert fresh_report['record_counts']['total'] == len(records)

    def test_record_counts(self, fresh_report):
        counts = fresh_report['record_counts']
        for field in ('total', 'scored', 'insufficient_inputs',
                      'not_supported', 'runner_error'):
            assert field in counts, field
            assert isinstance(counts[field], int)
        assert counts['total'] == (counts['scored']
                                   + counts['insufficient_inputs']
                                   + counts['not_supported']
                                   + counts['runner_error'])
        assert counts['scored'] > 0
        assert counts['runner_error'] == 0, fresh_report['skipped_summary']

    def test_cells(self, fresh_report):
        cells = fresh_report['cells']
        assert cells, 'hücre listesi boş'
        for cell in cells:
            for field in CELL_FIELDS:
                assert field in cell, (field, cell)
            assert cell['layer'] in VALID_LAYERS
            assert cell['n'] >= 1
            assert cell['worst_test_id']
        # Ana katmanda bilinen hücreler (tohum verisi kilidi)
        main = {(c['motor_type'], c['quantity'])
                for c in cells if c['layer'] == 'main'}
        assert ('hybrid', 'c_star') in main
        assert ('hybrid', 'regression_rate') in main
        assert ('solid', 'burn_rate') in main
        assert ('liquid', 'isp_vac') in main

    def test_skipped_summary(self, fresh_report):
        summary = fresh_report['skipped_summary']
        for field in ('status_counts', 'not_supported',
                      'insufficient_inputs', 'runner_errors',
                      'skipped_score_counts'):
            assert field in summary, field
        not_supported_ids = {item['test_id']
                             for item in summary['not_supported']}
        # G3 record_type düzeltmesi kilidi: fit/istatistik kayıtları artık
        # dürüstçe 'v1 kapsam dışı' olarak etiketlenir
        assert RETYPED_NOT_SUPPORTED <= not_supported_ids

    def test_markdown(self, fresh_report):
        md = fresh_report['markdown']
        assert md.startswith('# HRMA correlation summary')
        assert fresh_report['db_hash'] in md
          # v2.6.2 (F007): sütun "N" -> "N (campaigns)". Sayılan şey bağımsız
        # örnek değil KAMPANYA olduğu için başlık bunu açıkça söylüyor;
        # aynı motorun yakın çalışma noktaları tek kampanya sayılır.
        assert '| Motor | Quantity | N (campaigns) |' in md
        assert not any(ord(ch) > 0x2500 for ch in md), 'emoji/simge yasak'


class TestCache:
    def test_second_get_is_cached_and_identical(self, client, fresh_report):
        resp = client.get('/api/correlation-report')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['cached'] is True
        assert body['db_hash'] == fresh_report['db_hash']
        assert body['cells'] == fresh_report['cells']
        assert body['markdown'] == fresh_report['markdown']
        assert body['record_counts'] == fresh_report['record_counts']

    def test_refresh_forces_rerun(self, client, fresh_report):
        resp = client.post('/api/correlation-report', json={'refresh': True})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['cached'] is False  # önbellek yok sayıldı
        assert body['db_hash'] == fresh_report['db_hash']  # DB değişmedi
        assert body['cells'] == fresh_report['cells']  # koşucu deterministik

    def test_post_without_refresh_uses_cache(self, client, fresh_report):
        resp = client.post('/api/correlation-report', json={})
        assert resp.status_code == 200
        assert resp.get_json()['cached'] is True


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
