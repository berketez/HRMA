"""Sayfa varsayılanının katalog çözümünü ezmesi — bekçi (v2.6.27).

BULGU (15 Ağustos 2026, mimari tarama): ``solid.html`` yanma hızı alanlarını
``value="0.005"`` / ``value="0.35"`` ile dolduruyor ve toplama adımı boş alanı
``|| 0.005`` ile aynı sayıya düşürüyordu. Kullanıcı alana hiç dokunmasa da
sayfa 0.005 GÖNDERİYOR, arka ucun katalog çözümü (APCP a = 0.0022334,
``_PROPELLANT_CATALOG``) hiç çalışmıyordu. Ölçülen etki: aynı APCP motoru
yanma 2,67 s → 1,17 s (≈2,3×); kullanıcı kendi yazmadığı sayı yüzünden
katalog-dışı uyarısı görüyordu.

Çözüm: dokunulmamış alan payload'a HİÇ KONMAZ (boş → undefined →
JSON.stringify anahtarı düşürür); arka uç katalogdan çözer ve kaynağını
beyan eder. Bu dosya hem şablon tarafını hem API sözleşmesini kilitler.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOLID_SAYFA_HTML = (ROOT / 'hrma' / 'templates' / 'solid.html').read_text(
    encoding='utf-8')

LOCAL_HOST = {'Host': '127.0.0.1:8080'}

#: Sayfanın varsayılan yakıtıyla tutarlı, yanma hızı alanları OLMAYAN taban.
APCP_TABAN_YUK = {
    'propellant_name': 'APCP', 'grain_type': 'bates', 'grain_count': 3,
    'outer_diameter': 75.0, 'core_diameter': 32.0, 'grain_length': 360.0,
    'web_thickness': 21.5, 'grain_gap': 2.0, 'chamber_diameter': 75.0,
    'chamber_pressure': 40.0,
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _kos(client, **ek):
    r = client.post('/calculate_solid', json={**APCP_TABAN_YUK, **ek},
                    headers=LOCAL_HOST)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


# ---------------------------------------------------------------------------
# 1) Şablon tarafı: sabit varsayılan geri gelmesin
# ---------------------------------------------------------------------------
class TestSablonVarsayilani:

    def test_burn_rate_inputs_have_no_hardcoded_value(self):
        """``value="0.005"`` / ``value="0.35"`` şablona geri dönemez.

        Alanın ekrandaki varsayılanı, arka ucun katalog varsayılanıyla
        YARIŞAMAZ — aynı kavramın iki tanım noktası olamaz (parametre
        tutarlılığı kuralı). Boş alan + placeholder tek meşru durumdur.
        """
        a_input = re.search(r'<input[^>]*id="burn_rate_a"[^>]*>', SOLID_SAYFA_HTML)
        n_input = re.search(r'<input[^>]*id="burn_rate_n"[^>]*>', SOLID_SAYFA_HTML)
        assert a_input and n_input, 'yanma hızı alanları şablonda yok'
        assert 'value=""' in a_input.group(0), a_input.group(0)
        assert 'value=""' in n_input.group(0), n_input.group(0)
        # Boş alanın ne anlama geldiği kullanıcıya söylenmek zorunda.
        assert 'data-i18n-placeholder' in a_input.group(0)
        assert 'data-i18n-placeholder' in n_input.group(0)

    def test_collect_step_has_no_silent_fallback(self):
        """Toplama adımındaki ``|| 0.005`` / ``? 0.35`` düşüşleri yasak.

        O düşüşler boş alanı sayıya çevirip payload'a sokuyordu; boş alan
        artık ``undefined`` üretmeli (JSON.stringify anahtarı düşürür).
        """
        assert re.search(r"burn_rate_a.*\|\|\s*0\.005", SOLID_SAYFA_HTML) is None
        assert re.search(r"burn_rate_n'\)\.value\);\s*return isNaN\(v\)\s*\?"
                         r"\s*0\.35", SOLID_SAYFA_HTML) is None
        # Reset de sayı yazamaz.
        assert re.search(
            r"burn_rate_a'\)\.value\s*=\s*'0\.005'", SOLID_SAYFA_HTML) is None


# ---------------------------------------------------------------------------
# 2) API sözleşmesi: alan yokken katalog çözer
# ---------------------------------------------------------------------------
class TestApiSozlesmesi:

    def test_absent_field_means_catalog_not_page_default(self, client):
        """Alan gönderilmeyince sonuç, katalog a'sıyla gönderilene EŞİT;
        sayfanın eski 0.005 varsayılanıyla gönderilene EŞİT DEĞİL.

        Bu üçlü karşılaştırma, "alan yok" durumunun sessizce 0.005'e
        düşürülmediğini iki yönden kanıtlar.
        """
        from hrma.engines.solid_rocket_engine import (
            DEFAULT_BURN_RATE_A, DEFAULT_BURN_RATE_N)

        yok = _kos(client)
        katalog = _kos(client, burn_rate_a=DEFAULT_BURN_RATE_A,
                       burn_rate_n=DEFAULT_BURN_RATE_N)
        sayfa_eski = _kos(client, burn_rate_a=0.005, burn_rate_n=0.35)

        bt_yok = float(yok['burn_time'])
        bt_katalog = float(katalog['burn_time'])
        bt_eski = float(sayfa_eski['burn_time'])

        assert bt_yok == pytest.approx(bt_katalog, rel=1e-9), (
            'alan gönderilmeyince katalog değeri çözülmüyor')
        assert bt_yok != pytest.approx(bt_eski, rel=0.05), (
            'alan gönderilmeyince eski sayfa varsayılanı (0.005) '
            'kullanılmış — kusur geri gelmiş')

    def test_mutation_page_default_still_changes_result(self, client):
        """Mutasyon denetimi: bekçi tautoloji değil.

        0.005 göndermek sonucu GERÇEKTEN değiştiriyor (≈2,3×) — yani
        birinci test 'her şey aynı çıkıyor' diye değil, 'alan yokluğu
        katalog demek' olduğu için geçiyor.
        """
        yok = _kos(client)
        eski = _kos(client, burn_rate_a=0.005, burn_rate_n=0.35)
        oran = float(yok['burn_time']) / float(eski['burn_time'])
        assert oran > 1.5, (
            f'0.005 artık sonucu değiştirmiyor (oran {oran:.2f}) — '
            f'katalog a değeri 0.005 sınıfına mı kaydı? DEFAULT_BURN_RATE_A '
            f'değiştiyse bu testin taban beklentisi güncellenmeli.')
