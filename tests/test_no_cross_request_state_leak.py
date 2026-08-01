"""İstekler arası durum sızıntısı bekçisi.

NEDEN VAR
---------
`hrma/app.py` bazı çözümleyicileri MODÜL DÜZEYİNDE tekil nesne olarak kurar
(`trajectory_analyzer = TrajectoryAnalyzer()`, app.py:667). Tekil nesne
kendi başına yanlış değildir — ama bir istekte yazılan durum bir sonraki
istekte temizlenmezse, birebir aynı istek FARKLI sonuç döndürür.

v2.6.26'da bu ölçüldü ve gerçekti (paraşüt parametreleri):

    1. taban                  -> iniş hızı 22,62 m/s, parachute_area_assumed=True
    2. parachute_area=9.0     -> iniş hızı 10,65 m/s, assumed=False
    3. taban (1'in AYNISI)    -> iniş hızı 10,65 m/s, assumed=False   <-- SIZINTI

Üçüncü istek birinciyle bayt bayt aynıydı ve %53 farklı bir iniş hızı
döndürüyordu. Daha kötüsü: `parachute_area_assumed` bayrağı False'a düşüyor,
yani sistem UYDURULMUŞ bir değeri "kullanıcı verdi" diye işaretliyordu.
Yanlış sayıdan beteri budur — dürüstlük beyanının kendisi bozulur.

Masaüstü paketinde sızıntı süreç ömrü boyunca sürer; sunucu dağıtımında
kullanıcılar arasında sızar.

Bu bekçi, aynı isteğin arka arkaya AYNI sonucu vermesini sınar. Yeni bir
tekil çözümleyici eklenirse buraya bir vaka daha eklenmelidir.
"""

import contextlib
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADERS = {'Host': '127.0.0.1:8080'}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _sessiz_post(client, endpoint, payload):
    """Çözücü gürültüsünü yutarak POST atar."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        resp = client.post(endpoint, json=payload, headers=HEADERS)
    assert resp.status_code == 200, f'{endpoint} HTTP {resp.status_code}'
    return resp.get_json() or {}


def _hibrit_taban():
    """Katman B bekçisinin taban yükü — çözüldüğü doğrulanmış bir motor."""
    import sys
    sys.path.insert(0, str(ROOT))
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    return dict(HYBRID_BASE)


def _inis(sonuc):
    tm = ((sonuc.get('trajectory') or {}).get('performance') or {}) \
        .get('trajectory_metrics') or {}
    ph = (((sonuc.get('trajectory') or {}).get('trajectory') or {})
          .get('phases') or {}).get('descent') or {}
    return (tm.get('landing_velocity'), tm.get('parachute_area_m2'),
            tm.get('parachute_cd'), ph.get('parachute_area_assumed'))


class TestParachuteStateDoesNotLeak:
    """Paraşüt parametreleri bir sonraki isteğe taşınmamalı."""

    def test_identical_request_gives_identical_result(self, client):
        taban = _hibrit_taban()

        ilk = _inis(_sessiz_post(client, '/calculate', taban))
        # Arada paraşüt VEREN bir istek: tekil nesnenin durumunu değiştirir.
        _sessiz_post(client, '/calculate', dict(taban, parachute_area=9.0))
        ikinci = _inis(_sessiz_post(client, '/calculate', taban))

        assert ilk == ikinci, (
            'Birebir aynı istek farklı sonuç döndürdü — istekler arası durum '
            f'sızıntısı. ilk={ilk} ikinci={ikinci}')

    def test_supplied_value_is_honoured_then_forgotten(self, client):
        taban = _hibrit_taban()

        varsayilan = _inis(_sessiz_post(client, '/calculate', taban))
        verilen = _inis(_sessiz_post(client, '/calculate',
                                     dict(taban, parachute_area=9.0)))
        sonra = _inis(_sessiz_post(client, '/calculate', taban))

        assert verilen[1] == pytest.approx(9.0), \
            'kullanıcının verdiği paraşüt alanı uygulanmadı'
        assert verilen[3] is False, \
            'kullanıcı değer verdiği hâlde "varsayıldı" bayrağı düşmedi'
        assert sonra == varsayilan, \
            'verilen değer sonraki isteğe sızdı'
        assert sonra[3] is True, (
            'varsayılan değere dönüldüğü hâlde "varsayıldı" bayrağı '
            'kullanıcı vermiş gibi işaretli kaldı')

    def test_cd_alone_does_not_pin_area(self, client):
        """Bir anahtarı vermek DİĞERLERİNİ de sıfırlamalı.

        Eski kod yalnız VERİLEN anahtarları varsayılana çekiyordu; bu yüzden
        bir istekte alan, sonrakinde Cd verilince alan hâlâ eski isteğinki
        kalıyordu.
        """
        taban = _hibrit_taban()

        _sessiz_post(client, '/calculate', dict(taban, parachute_area=9.0))
        yalniz_cd = _inis(_sessiz_post(client, '/calculate',
                                       dict(taban, parachute_cd=0.9)))

        assert yalniz_cd[2] == pytest.approx(0.9), 'verilen Cd uygulanmadı'
        assert yalniz_cd[1] != pytest.approx(9.0), (
            'önceki isteğin paraşüt ALANI bu isteğe taşındı — kısmi '
            'sıfırlama hatası')
