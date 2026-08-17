"""/api/analysis/combustion-stability uç bekçileri (parti 28, A2).

Uç, hrma/stability çekirdeğinin (chug + damping) HTTP bağlamasıdır ve
``thermal_protection_analysis`` ucunun İKİZİ desenini taşır: mode kapısı +
zorunlu alan kapısı (422 ``missing_fields``) + çekirdek ValueError → 400.

Kilitlenen sözleşmeler:

(a) ``assessment``, ``assess_chug()`` sözlüğünün BİT-AYNI geçişidir (yeniden
    adlandırma yasak): aynı girdilerle doğrudan çekirdek çağrısıyla tam
    sözlük eşitliği aranır (JSON gidiş-dönüşü Python float'ları bit korur).
(b) ``neutral_curve`` her noktada ``chug_neutral_tau_ratio`` ile bit-aynı,
    en az 60 örnek, bant [0,02, 0,48].
(c) ``root_locus`` her noktada ``chug_rightmost_root`` ile bit-aynı (aynı
    işletme τ/τ_c/τ_f); atlanan nokta ``skipped_points``te beyanlı.
(d) ``feed_line`` → τ_f türetimi ``feed_inertance_time_constant`` ile
    bit-aynı; dairesel kesit çevirisi motor tarafıyla aynı formül
    (A = π·(d/1000)²/4); ``density_kg_m3`` YALNIZ yankıdır, hesabı
    değiştirmez (bit-ölçümlü negatif kanıt).
(e) 422 gövdesi makine-okur (status/error/mode/missing_fields), 400 zinciri
    (bilinmeyen mod, mode'suz gövde, sayı olmayan girdi, çekirdek
    ValueError), boş feed_line alt alanları 422.
(f) Uç kendi eklediği katmanda hüküm anahtarı TAŞIMAZ:
    ``forbid_verdict_key`` kabuk üstünde geçer; pozitif kontrol olarak
    assessment dahil edilince (çekirdeğin meşru hükmü) aynı bekçi yakalar —
    yani bekçi canlıdır, sessiz yeşil değildir.
(g) İki route (/api/combustion-stability ve /api/analysis/…) aynı gövdeyi
    verir.

MUTASYON ÖLÇÜMÜ (elle yapıldı, ters-değiştirmeyle geri alındı; rapora
kaydedildi): app.py'deki zorunlu alan kapısı gevşetilince (``missing``
listesi hep boş yapılınca) bu dosyanın 422 bekçileri kırmızı yanar —
eksik girdi çekirdeğe sızıp 400 ham ValueError üretir, 422 sözleşmesi
kaybolur.
"""

import math

import pytest

from hrma.app import app
from hrma.stability.chug import (
    assess_chug,
    chug_neutral_tau_ratio,
    chug_rightmost_root,
    feed_inertance_time_constant,
)
from hrma.stability.damping import (
    damping_budget,
    nozzle_damping_quasi_steady,
)
from hrma.stability import forbid_verdict_key

LOCAL_HOST = {'Host': '127.0.0.1:8080'}
URL = '/api/analysis/combustion-stability'
URL_KISA = '/api/combustion-stability'

# Tasarım belgesi §3.2'nin tipik sıvı vakası (tests/test_stability_cekirdek.py
# ile aynı çapa): J = 0,20, τ_c = 1,3209 ms; τ = 1,0 ms nötrün (1,1428 ms)
# ALTINDA kalır → stable.
DOC_J = 0.2
DOC_TAU_C_S = 1.3208873639398158e-3
DOC_TAU_S = 1.0e-3

# Culick & Yang 1990'ın kendi örnek motoru (hrma/stability/damping.py
# docstring çapası): α ≈ −160,25 1/s (makale Tablo 1: −160,1).
CY_PAYLOAD = {
    'mode': 'damping',
    'sound_speed_m_s': 1075.0,
    'chamber_length_m': 0.5969,
    'gamma': 1.18,
    'nozzle_entrance_mach': 0.08163,
}


@pytest.fixture()
def client():
    with app.test_client() as c:
        yield c


def _chug_payload(**over):
    payload = {'mode': 'chug', 'dp_ratio_j': DOC_J, 'tau_s': DOC_TAU_S,
               'tau_c_s': DOC_TAU_C_S}
    payload.update(over)
    return payload


# ===========================================================================
# (a) chug 200 — assessment bit-aynı geçiş + zarf anahtarları
# ===========================================================================
def test_chug_assessment_cekirdekle_bit_ayni(client):
    """assessment == assess_chug(aynı girdiler): tam sözlük eşitliği.

    JSON gidiş-dönüşü Python float'larını bit-aynı korur (repr en kısa
    gidiş-dönüş gösterimi); dolayısıyla == karşılaştırması yeniden
    adlandırmayı da, en küçük sayısal ara katman hesabını da yakalar.
    """
    r = client.post(URL, json=_chug_payload(), headers=LOCAL_HOST)
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] == 'ok'
    assert body['mode'] == 'chug'
    direct = assess_chug(dp_ratio_j=DOC_J, tau_s=DOC_TAU_S,
                         tau_c_s=DOC_TAU_C_S)
    assert body['assessment'] == direct
    # Hüküm çekirdekten kapsam etiketli gelir — nötr altı → stable.
    assert body['assessment']['verdict'] == 'stable'
    assert body['assessment']['verdict_scope']
    # Zarf anahtarları (uç sözleşmesi).
    assert set(body) == {'status', 'mode', 'assessment', 'neutral_curve',
                        'root_locus', 'operating_point'}


def test_chug_operating_point_bit_ayni(client):
    r = client.post(URL, json=_chug_payload(), headers=LOCAL_HOST)
    body = r.get_json()
    op = body['operating_point']
    assert op['dp_ratio_j'] == body['assessment']['dp_ratio_j']
    assert op['tau_over_tau_c'] == body['assessment']['tau_over_tau_c']
    assert op['tau_over_tau_c'] == DOC_TAU_S / DOC_TAU_C_S


def test_chug_unstable_vakasi(client):
    """τ nötrün üstünde → çekirdek hükmü unstable, uç aynen taşır."""
    r = client.post(URL, json=_chug_payload(tau_s=2.0e-3),
                    headers=LOCAL_HOST)
    assert r.status_code == 200
    a = r.get_json()['assessment']
    assert a['verdict'] == 'unstable'
    assert a == assess_chug(dp_ratio_j=DOC_J, tau_s=2.0e-3,
                            tau_c_s=DOC_TAU_C_S)


def test_chug_kosulsuz_kararli_j_yarim_ustu(client):
    """J ≥ 0,5: çekirdek koşulsuz kararlı der; uç 200 ile aynen taşır."""
    r = client.post(URL, json=_chug_payload(dp_ratio_j=0.6),
                    headers=LOCAL_HOST)
    assert r.status_code == 200
    body = r.get_json()
    a = body['assessment']
    assert a['unconditionally_stable'] is True
    assert a['verdict'] == 'stable'
    assert a['neutral_delay_s'] is None
    # Nötr eğri işletme J'sinden bağımsız yayımlanır (çizim bandı).
    assert len(body['neutral_curve']['dp_ratio_j']) >= 60


# ===========================================================================
# (b) nötr eğri — bit-aynılık + örnekleme sözleşmesi
# ===========================================================================
def test_notr_egri_orneklemesi_ve_bit_ayniligi(client):
    r = client.post(URL, json=_chug_payload(), headers=LOCAL_HOST)
    curve = r.get_json()['neutral_curve']
    js, ratios = curve['dp_ratio_j'], curve['tau_over_tau_c']
    assert len(js) == len(ratios) >= 60
    assert js[0] == pytest.approx(0.02, abs=1e-12)
    assert js[-1] == pytest.approx(0.48, abs=1e-12)
    assert js == sorted(js)
    # Bit-aynılık: uç, yayımladığı J'nin KENDİSİYLE çekirdeği çağırmış
    # olmalı — üç noktada tam eşitlik (approx değil).
    for k in (0, len(js) // 2, len(js) - 1):
        assert ratios[k] == chug_neutral_tau_ratio(js[k])
    # Sayısal çapa: J = 0,20 noktası eğrinin üzerinde ve 0,8652 değerinde.
    mid = min(range(len(js)), key=lambda i: abs(js[i] - DOC_J))
    assert ratios[mid] == pytest.approx(0.8651523967380913, rel=1e-9)


# ===========================================================================
# (c) kök yeri — bit-aynılık + hizalama + skipped_points beyanı
# ===========================================================================
def test_kok_yeri_cekirdekle_bit_ayni(client):
    r = client.post(URL, json=_chug_payload(), headers=LOCAL_HOST)
    body = r.get_json()
    locus = body['root_locus']
    js = locus['dp_ratio_j']
    assert len(js) == len(locus['sigma_1_s']) == len(locus['frequency_hz'])
    assert isinstance(locus['skipped_points'], list)
    assert len(js) + len(locus['skipped_points']) == 41
    # İşletme J'si çevresinde: pencere [0,1, 0,3] (merkez 0,2, ±0,1).
    assert min(js) == pytest.approx(0.1, abs=1e-12)
    assert max(js) == pytest.approx(0.3, abs=1e-12)
    tau = body['assessment']['tau_s']
    tau_c = body['assessment']['tau_c_s']
    for k in (0, len(js) // 2, len(js) - 1):
        root = chug_rightmost_root(js[k], tau, tau_c, 0.0)
        assert locus['sigma_1_s'][k] == float(root.real)
        assert locus['frequency_hz'][k] == abs(float(root.imag)) / (
            2.0 * math.pi)


def test_kok_yeri_penceresi_banda_kistirilir(client):
    """İşletme J'si bandın dışındaysa pencere bandın içine kaydırılır."""
    r = client.post(URL, json=_chug_payload(dp_ratio_j=0.6),
                    headers=LOCAL_HOST)
    js = r.get_json()['root_locus']['dp_ratio_j']
    assert min(js) >= 0.02 - 1e-12
    assert max(js) <= 0.48 + 1e-12
    assert max(js) == pytest.approx(0.48, abs=1e-12)


# ===========================================================================
# (d) feed_line → τ_f türetimi
# ===========================================================================
FEED_LINE = {'length_m': 2.0, 'diameter_mm': 25.0, 'mass_flow_kg_s': 1.2,
             'dp_injector_Pa': 5.0e5}


def test_feed_line_tau_f_turetimi_bit_ayni(client):
    r = client.post(URL, json=_chug_payload(feed_line=dict(FEED_LINE)),
                    headers=LOCAL_HOST)
    assert r.status_code == 200
    a = r.get_json()['assessment']
    area = math.pi * (25.0 / 1000.0) ** 2 / 4.0
    beklenen = feed_inertance_time_constant(2.0, area, 1.2, 5.0e5)
    assert a['inertance_included'] is True
    assert a['tau_f_s'] == beklenen
    echo = a['feed_line']
    assert echo['line_length_m'] == 2.0
    assert echo['line_area_m2'] == area
    assert echo['line_diameter_mm'] == 25.0
    assert echo['mass_flow_kg_s'] == 1.2
    assert echo['dp_injector_Pa'] == 5.0e5
    assert '_basis' in echo


def test_feed_line_area_dogrudan(client):
    """area_m2 verilirse çap istenmez ve çevirme yapılmaz."""
    fl = {'length_m': 2.0, 'area_m2': 4.9e-4, 'mass_flow_kg_s': 1.2,
          'dp_injector_Pa': 5.0e5}
    r = client.post(URL, json=_chug_payload(feed_line=fl),
                    headers=LOCAL_HOST)
    assert r.status_code == 200
    a = r.get_json()['assessment']
    assert a['tau_f_s'] == feed_inertance_time_constant(2.0, 4.9e-4, 1.2,
                                                        5.0e5)
    assert a['feed_line']['line_area_m2'] == 4.9e-4
    assert 'line_diameter_mm' not in a['feed_line']


def test_feed_line_yogunluk_yalniz_yanki(client):
    """density_kg_m3 yankılanır ama τ_f'yi DEĞİŞTİRMEZ (bit-ölçüm).

    Birinci mertebe atalet formu τ_f = ℓ·ṁ/(2·A·ΔP) yoğunluğu içermez;
    sözleşmedeki alan yalnız kayıt içindir. Yoğunluklu ve yoğunluksuz iki
    istek bit-aynı τ_f verir, yankıda alan durur.
    """
    fl_yogun = dict(FEED_LINE, density_kg_m3=800.0)
    r1 = client.post(URL, json=_chug_payload(feed_line=fl_yogun),
                     headers=LOCAL_HOST)
    r2 = client.post(URL, json=_chug_payload(feed_line=dict(FEED_LINE)),
                     headers=LOCAL_HOST)
    a1, a2 = r1.get_json()['assessment'], r2.get_json()['assessment']
    assert a1['tau_f_s'] == a2['tau_f_s']
    assert a1['feed_line']['density_kg_m3'] == 800.0
    assert 'density_kg_m3' not in a2['feed_line']


def test_tau_f_dogrudan_verilirse_feed_line_kullanilmaz(client):
    """tau_f_s doğrudan verilince o kullanılır; feed_line yalnız yankı olur."""
    r = client.post(URL, json=_chug_payload(tau_f_s=2.0e-3,
                                            feed_line=dict(FEED_LINE)),
                    headers=LOCAL_HOST)
    assert r.status_code == 200
    a = r.get_json()['assessment']
    assert a['tau_f_s'] == 2.0e-3
    assert a['inertance_included'] is True
    assert 'NOT used' in a['feed_line']['_basis']
    # Doğrudan çekirdek çağrısıyla da bit-aynı (feed_line yankısı dahil).
    direct = assess_chug(dp_ratio_j=DOC_J, tau_s=DOC_TAU_S,
                         tau_c_s=DOC_TAU_C_S, tau_f_s=2.0e-3,
                         feed_line=dict(FEED_LINE, _basis=(
                             'Echo only: tau_f_s was supplied directly by '
                             'the caller, so this feed_line block was NOT '
                             'used to derive it.')))
    assert r.get_json()['assessment'] == direct


def test_feed_line_eksik_alt_alan_422(client):
    """feed_line verilir ama ΔP_inj eksikse: 422 + adıyla beyan.

    (Uç sözleşmesi listesinde dp_injector_Pa yoktu; formül onsuz kapanmadığı
    için uç onu zorunlu alır ve eksikliği makine-okur bildirir — uydurma
    ΔP türetilmez.)
    """
    fl = {'length_m': 2.0, 'diameter_mm': 25.0, 'mass_flow_kg_s': 1.2,
          'density_kg_m3': 800.0}
    r = client.post(URL, json=_chug_payload(feed_line=fl),
                    headers=LOCAL_HOST)
    assert r.status_code == 422
    body = r.get_json()
    assert body['error'] == 'incomplete_combustion_stability_input'
    assert body['mode'] == 'chug'
    assert body['missing_fields'] == ['feed_line.dp_injector_Pa']


def test_feed_line_alan_ve_cap_ikisi_de_yoksa_422(client):
    fl = {'length_m': 2.0, 'mass_flow_kg_s': 1.2, 'dp_injector_Pa': 5.0e5}
    r = client.post(URL, json=_chug_payload(feed_line=fl),
                    headers=LOCAL_HOST)
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == [
        'feed_line.area_m2 | feed_line.diameter_mm']


def test_feed_line_sozluk_degilse_400(client):
    r = client.post(URL, json=_chug_payload(feed_line=3.0),
                    headers=LOCAL_HOST)
    assert r.status_code == 400
    assert 'feed_line' in r.get_json()['error']


# ===========================================================================
# (e) damping 200 — çekirdek sözlükleri AYNEN
# ===========================================================================
def test_damping_cekirdekle_bit_ayni(client):
    r = client.post(URL, json=dict(CY_PAYLOAD), headers=LOCAL_HOST)
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] == 'ok'
    assert body['mode'] == 'damping'
    assert set(body) == {'status', 'mode', 'nozzle', 'budget'}
    nozzle = nozzle_damping_quasi_steady(
        sound_speed_m_s=1075.0, chamber_length_m=0.5969, gamma=1.18,
        nozzle_entrance_mach=0.08163)
    assert body['nozzle'] == nozzle
    assert body['budget'] == damping_budget([nozzle])
    # Culick & Yang örnek motoru çapası (Tablo 1: −160,1; formül −160,25).
    assert body['nozzle']['damping_1_s'] == pytest.approx(-160.25, rel=2e-3)
    assert body['budget']['terms'] == {'nozzle': nozzle['damping_1_s']}
    assert body['budget']['total_loss_1_s'] == -nozzle['damping_1_s']


# ===========================================================================
# (f) 422 / 400 kapıları
# ===========================================================================
def test_chug_eksik_alanlar_422_govdesi(client):
    r = client.post(URL, json={'mode': 'chug', 'dp_ratio_j': DOC_J},
                    headers=LOCAL_HOST)
    assert r.status_code == 422
    body = r.get_json()
    assert body['status'] == 'error'
    assert body['error'] == 'incomplete_combustion_stability_input'
    assert body['mode'] == 'chug'
    assert body['missing_fields'] == ['tau_s', 'tau_c_s']
    assert 'no default' in body['message']


def test_damping_eksik_alanlar_422_govdesi(client):
    r = client.post(URL, json={'mode': 'damping',
                               'sound_speed_m_s': 1075.0,
                               'chamber_length_m': ''},
                    headers=LOCAL_HOST)
    assert r.status_code == 422
    body = r.get_json()
    assert body['mode'] == 'damping'
    # Boş dize de eksik sayılır (panel boş alanı '' gönderebilir).
    assert body['missing_fields'] == ['chamber_length_m', 'gamma',
                                     'nozzle_entrance_mach']


def test_bilinmeyen_mode_400(client):
    r = client.post(URL, json={'mode': 'screech'}, headers=LOCAL_HOST)
    assert r.status_code == 400
    err = r.get_json()['error']
    assert 'screech' in err
    assert 'chug' in err and 'damping' in err


def test_modsuz_govde_400(client):
    """mode'un varsayılanı yok: boş JSON nesnesi 400 alır (sessiz seçim yok)."""
    r = client.post(URL, json={}, headers=LOCAL_HOST)
    assert r.status_code == 400
    assert 'mode' in r.get_json()['error'].lower()


def test_sayi_olmayan_girdi_400(client):
    r = client.post(URL, json=_chug_payload(dp_ratio_j='abc'),
                    headers=LOCAL_HOST)
    assert r.status_code == 400
    assert 'dp_ratio_j' in r.get_json()['error']


def test_cekirdek_valueerror_400(client):
    """Negatif τ çekirdeğin kapısına takılır; uç 400 + metni aynen iletir."""
    r = client.post(URL, json=_chug_payload(tau_s=-1.0e-3),
                    headers=LOCAL_HOST)
    assert r.status_code == 400
    assert 'tau_s' in r.get_json()['error']


def test_damping_gamma_bandi_400(client):
    r = client.post(URL, json=dict(CY_PAYLOAD, gamma=2.5),
                    headers=LOCAL_HOST)
    assert r.status_code == 400
    assert 'gamma' in r.get_json()['error']


# ===========================================================================
# (g) hüküm disiplini — uç katmanı hükümsüz
# ===========================================================================
def test_uc_katmani_hukum_anahtari_tasimaz(client):
    """Kabuk (assessment hariç) forbid_verdict_key'den geçer.

    Pozitif kontrol: assessment DAHİL edilince aynı bekçi ValueError atar
    (çekirdeğin meşru, kapsam etiketli hükmü oradadır) — yani bekçi gerçekten
    'verdict' arıyor, sessiz yeşil değil.
    """
    r = client.post(URL, json=_chug_payload(), headers=LOCAL_HOST)
    body = r.get_json()
    kabuk = {k: v for k, v in body.items() if k != 'assessment'}
    forbid_verdict_key(kabuk, 'api/combustion-stability chug kabuk')
    with pytest.raises(ValueError):
        forbid_verdict_key(body, 'pozitif kontrol')


def test_damping_yaniti_tamamen_hukumsuz(client):
    """Sönüm yolu akustik yoldur: yanıtın HİÇBİR yerinde hüküm olamaz."""
    r = client.post(URL, json=dict(CY_PAYLOAD), headers=LOCAL_HOST)
    forbid_verdict_key(r.get_json(), 'api/combustion-stability damping')


# ===========================================================================
# (h) route çifti
# ===========================================================================
def test_iki_route_ayni_govdeyi_verir(client):
    for payload in (_chug_payload(), dict(CY_PAYLOAD)):
        r1 = client.post(URL, json=payload, headers=LOCAL_HOST)
        r2 = client.post(URL_KISA, json=payload, headers=LOCAL_HOST)
        assert r1.status_code == r2.status_code == 200
        assert r1.get_json() == r2.get_json()
