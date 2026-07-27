"""Sonlu olmayan çıktı değerleri bekçisi (v2.6.2).

Neden bu test var — sessiz veri bozulması zinciri:

``sanitize_json_values`` neredeyse TÜM API yanıtlarının son filtresidir
(50 çağrı yeri). Eskiden ``NaN → 0.0`` ve ``Inf → ±1e10`` dönüşümü yapıyordu,
yani hesabın içinde oluşan her sayısal hata kullanıcıya GEÇERLİ BİR ÖLÇÜM gibi
görünüyordu: sıfıra bölme, negatif karekök veya ıraksayan bir çözücü ekranda
"0.00" olarak beliriyordu.

Zincirin tamamı:
  1. Dört üretim modülü ``warnings.filterwarnings('ignore')`` çağırıyor.
     Argümansız çağrı SÜREÇ GENELİNDE catch-all filtre kurar — kapsam yazanın
     modülü değil, tüm Python süreci.
  2. Bu yüzden numpy'nin divide-by-zero / invalid-value uyarısı hiç görünmüyor.
  3. NaN üretiliyor.
  4. ``sanitize_json_values`` NaN'ı 0.0 yapıyor.
  5. Panel bunu gerçek ölçüm gibi gösteriyor.

Girdi tarafı 2026-07-23'te kapatılmıştı (``_reject_non_finite``); bu testler
ÇIKTI tarafını kilitler.
"""

import math

import numpy as np
import pytest

from hrma.app import sanitize_json_values


class TestNonFiniteBecomesNull:
    @pytest.mark.parametrize('value', [
        float('nan'), float('inf'), float('-inf'),
        np.float64('nan'), np.float64('inf'), np.float64('-inf'),
        np.float32('nan'),
    ])
    def test_non_finite_scalar_is_none(self, value):
        assert sanitize_json_values(value) is None

    def test_nan_does_not_become_zero(self):
        """En kritik iddia: NaN sıfıra dönüşmemeli."""
        assert sanitize_json_values(float('nan')) != 0.0

    def test_inf_does_not_become_large_number(self):
        """Inf, 1e10 gibi 'makul görünen' bir sayıya dönüşmemeli."""
        out = sanitize_json_values(float('inf'))
        assert out is None
        assert out != 1e10

    def test_real_zero_is_preserved(self):
        """GERÇEK sıfır korunmalı — eksik veriden ayırt edilebilmeli.

        Düzeltmenin anlamı bu ayrımda: 0.0 bir ölçüm, None ise 'hesaplanamadı'.
        """
        assert sanitize_json_values(0.0) == 0.0
        assert sanitize_json_values(0.0) is not None
        assert sanitize_json_values(np.float64(0.0)) == 0.0

    def test_ordinary_values_pass_through(self):
        assert sanitize_json_values(123.456) == pytest.approx(123.456)
        assert sanitize_json_values(42) == 42
        assert sanitize_json_values(True) is True
        assert sanitize_json_values('metin') == 'metin'
        assert sanitize_json_values(None) is None


class TestNestedStructures:
    def test_dict_values(self):
        out = sanitize_json_values({'isp': float('nan'), 'thrust': 5000.0})
        assert out['isp'] is None
        assert out['thrust'] == 5000.0

    def test_list_and_tuple(self):
        assert sanitize_json_values([1.0, float('nan'), 3.0]) == [1.0, None, 3.0]
        assert sanitize_json_values((float('inf'), 2.0)) == [None, 2.0]

    def test_numpy_array(self):
        out = sanitize_json_values(np.array([1.0, np.nan, np.inf, 4.0]))
        assert out == [1.0, None, None, 4.0]

    def test_deeply_nested(self):
        payload = {'a': {'b': [{'c': float('nan')}, {'c': 1.0}]}}
        out = sanitize_json_values(payload)
        assert out['a']['b'][0]['c'] is None
        assert out['a']['b'][1]['c'] == 1.0

    def test_result_is_json_serialisable_without_allow_nan(self):
        """Çıktı, NaN'a izin vermeyen katı JSON ile serileştirilebilmeli.

        json.dumps varsayılanı NaN'ı 'NaN' diye yazar (geçersiz JSON);
        allow_nan=False ile sınamak sızıntıyı yakalar.
        """
        import json
        payload = {'x': float('nan'), 'y': [float('inf'), 1.0],
                   'z': np.array([np.nan, 2.0])}
        text = json.dumps(sanitize_json_values(payload), allow_nan=False)
        assert 'NaN' not in text and 'Infinity' not in text


def test_source_has_no_nan_to_zero_coercion():
    """Statik bekçi: dönüşümün koda geri sızmasını engeller."""
    import inspect
    import re

    import hrma.app as appmod

    src = inspect.getsource(appmod.sanitize_json_values)
    body = src[src.index('"""', src.index('"""') + 3) + 3:]  # docstring'i at
    assert not re.search(r'return\s+0\.0', body), (
        'sanitize_json_values yine 0.0 döndürüyor — NaN maskeleniyor olabilir')
    assert '1e10' not in body, 'Inf yine büyük bir sayıya çevriliyor'
