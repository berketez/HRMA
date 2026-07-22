"""Burn-rate preset bağlantısı testleri (tasarım yolu <-> merkezi db).

Kapsam:
  1. resolve_engine_coeffs birim dönüşümü: motor konvansiyonundaki (a, n)
     ile db'nin mm/s-MPa konvansiyonu AYNI yanma hızını üretmeli.
  2. Rejim seçimi: basınç değişince doğru parçalı rejim katsayısı gelmeli
     (KNDX plateau n<0 rejimi dahil).
  3. /api/burn-rate/resolve sözleşmesi: alanlar, hata durumları.
  4. Tasarım yolu entegrasyonu: /calculate_solid negatif n'li (plateau)
     preset katsayılarını REDDETMEMELİ (eski [0.1, 1.0] doğrulama bugı).
"""

import pytest

from hrma.data import burn_rate_db


@pytest.fixture()
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestResolveEngineCoeffs:
    @pytest.mark.parametrize("prop", ["kndx", "knsb"])
    @pytest.mark.parametrize("p_bar", [5.0, 15.0, 40.0, 70.0, 100.0])
    def test_engine_units_reproduce_db_rate(self, prop, p_bar):
        """Motor konvansiyonu (a, n) db yanma hızını birebir üretmeli."""
        res = burn_rate_db.resolve_engine_coeffs(prop, p_bar)
        r_engine_mps = res["a"] * p_bar ** res["n"]
        r_db_mps = burn_rate_db.burn_rate_mps(prop, p_bar * 1e5)
        assert r_engine_mps == pytest.approx(r_db_mps, rel=1e-12)

    def test_kndx_plateau_regime_negative_n(self):
        """KNDX 5.93-8.5 MPa (59.3-85 bar) rejimi mesa: n=-0.148."""
        res = burn_rate_db.resolve_engine_coeffs("kndx", 70.0)
        assert res["n"] == pytest.approx(-0.148)
        assert res["in_range"] is True

    def test_regime_switches_with_pressure(self):
        low = burn_rate_db.resolve_engine_coeffs("kndx", 5.0)
        high = burn_rate_db.resolve_engine_coeffs("kndx", 40.0)
        assert (low["a"], low["n"]) != (high["a"], high["n"])

    def test_out_of_range_flagged(self):
        res = burn_rate_db.resolve_engine_coeffs("knsb", 150.0)
        assert res["in_range"] is False

    def test_unknown_propellant_raises(self):
        with pytest.raises(KeyError):
            burn_rate_db.resolve_engine_coeffs("apcp", 40.0)

    def test_source_citation_present(self):
        res = burn_rate_db.resolve_engine_coeffs("knsb", 40.0)
        assert "Nakka" in res["source"]
        assert res["name"].startswith("Potassium Nitrate")


class TestResolveEndpoint:
    def test_contract_fields(self, client):
        r = client.post('/api/burn-rate/resolve',
                        json={'propellant': 'kndx', 'pressure_bar': 40.0})
        assert r.status_code == 200
        d = r.get_json()
        assert d['status'] == 'success'
        for key in ('a', 'n', 'r_mmps', 'regime', 'in_range',
                    'name', 'source', 'propellant', 'pressure_bar'):
            assert key in d, key
        assert d['regime']['p_min_mpa'] < d['regime']['p_max_mpa']

    def test_unknown_propellant_400(self, client):
        r = client.post('/api/burn-rate/resolve',
                        json={'propellant': 'apcp', 'pressure_bar': 40.0})
        assert r.status_code == 400
        assert 'Available' in r.get_json()['error']

    def test_bad_pressure_400(self, client):
        for bad in (0, -5, 5000):
            r = client.post('/api/burn-rate/resolve',
                            json={'propellant': 'kndx', 'pressure_bar': bad})
            assert r.status_code == 400

    def test_matches_module(self, client):
        r = client.post('/api/burn-rate/resolve',
                        json={'propellant': 'knsb', 'pressure_bar': 25.0})
        d = r.get_json()
        ref = burn_rate_db.resolve_engine_coeffs('knsb', 25.0)
        assert d['a'] == pytest.approx(ref['a'])
        assert d['n'] == pytest.approx(ref['n'])


class TestDesignPathAcceptsPlateauN:
    def test_calculate_solid_negative_n_not_rejected(self, client):
        """KNDX 70 bar plateau preset'i (n=-0.148) tasarım yolundan geçmeli.

        Eski doğrulama aralığı [0.1, 1.0] bu fiziksel katsayıyı 400 ile
        reddediyordu; aralık [-0.5, 1.0] olarak düzeltildi.
        """
        coeffs = burn_rate_db.resolve_engine_coeffs('kndx', 70.0)
        payload = {
            'grain_type': 'bates',
            'chamber_diameter': 100,
            'grain_length': 400,
            'core_diameter': 30,
            'chamber_pressure': 70.0,
            'burn_rate_a': coeffs['a'],
            'burn_rate_n': coeffs['n'],
            'burn_rate_preset': 'kndx',
        }
        r = client.post('/calculate_solid', json=payload)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        d = r.get_json()
        assert d.get('status') != 'error'

    def test_calculate_solid_still_rejects_absurd_n(self, client):
        payload = {
            'grain_type': 'bates',
            'chamber_diameter': 100,
            'grain_length': 400,
            'core_diameter': 30,
            'chamber_pressure': 40.0,
            'burn_rate_a': 0.005,
            'burn_rate_n': -2.0,
        }
        r = client.post('/calculate_solid', json=payload)
        assert r.status_code == 400
