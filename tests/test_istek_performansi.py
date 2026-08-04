"""İstek performansı bekçileri — P-6, P-5 ve konsol gürültüsü.

Kaynak denetim: scratchpad/perf_audit_v262.md. Bu dosya üç bakım kalemini
kilitler; hepsi davranış-uyumludur (varsayılan yanıt DEĞİŞMEZ):

  [P-6] /calculate gövdesindeki ``include_plots`` alanı: false gönderen
        istemci 10 Plotly figürünün üretimini TOPTAN atlar, ``plots``
        anahtarı açıkça null döner (boş figür uydurulmaz). Alan verilmezse
        tam figür seti üretilir — eski davranış birebir.
        ÖLÇÜLDÜ (2026-08-04, M4 Max, medyan/3, sıcak süreç):
        varsayılan 1832 ms / 2241 KB → include_plots=false 1642 ms / 1173 KB
        (süre −%10, yanıt −%48; süre farkının audit'teki %54'ten küçük
        olması ölçüm ağacının farkı — sayılar buradaki koşudan).

  [P-5] ``?slim=1`` sorgu parametresi ön yüzün HİÇ okumadığı iki ağır alanı
        düşürür: ``trajectory.trajectory`` (597,8 KB ham zaman serisi) ve
        ``trajectory.motor_data`` (üst seviye ``motor`` ile bit-aynı kopya).
        Düşürülen alanlar ``omitted_fields`` ile AÇIKÇA beyan edilir.
        ÖLÇÜLDÜ: slim 1704 KB (−%24); include_plots=false + slim
        637 KB (−%72).

  [Konsol] /calculate_liquid motor iç döngüleri aynı bilgi satırlarını
        yüzlerce kez basıyordu. ÖLÇÜLDÜ (2026-08-04): tek çağrıda 301 satır,
        105 benzersiz ("NASA Validation" bloğu 27, "Effective C* set"
        satırları 4'er kez). app.py::_dedup_engine_stdout her benzersiz
        satırı BİR kez basar, kapanışta sayım beyan eder → aynı çağrı artık
        ~102 satır, tekrar 0. Bilgi silinmez, tekrar kesilir.
"""

import collections
import json
import re
import time

import pytest

#: Küçük ama eksiksiz hibrit yükü (yörünge + figürler dahil çalışır).
HYBRID_PAYLOAD = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 7.0,
    'chamber_pressure': 30, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'injector_type': 'showerhead',
}

#: NASA doğrulayıcısını tetikleyen sıvı yükü (rp1/lox → F-1 karşılaştırması);
#: konsol gürültüsü bu yolda ölçüldü.
LIQUID_PAYLOAD = {
    'thrust': 25000, 'chamber_pressure': 70, 'mixture_ratio': 2.3,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
}

#: Varsayılan /calculate yanıtındaki figür anahtarları (şema kilidi).
EXPECTED_PLOT_KEYS = {
    'motor', 'injector', 'performance', 'trajectory', 'altitude_performance',
    'mass_fractions', 'thrust_altitude', 'combustion_analysis',
    'realtime_dashboard', 'motor_3d',
}

#: slim=1'in düşürdüğü yörünge alanları (perf_audit_v262 [P-5] listesi).
SLIM_OMITTED_TRAJECTORY_FIELDS = {'trajectory', 'motor_data'}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


# Hesap pahalı (~2 s/istek) — her varyant modül başına BİR kez istenir.
_CACHE = {}


def _response(client, name, payload_extra=None, query=''):
    if name not in _CACHE:
        body = dict(HYBRID_PAYLOAD)
        if payload_extra:
            body.update(payload_extra)
        t0 = time.perf_counter()
        resp = client.post('/calculate' + query, json=body)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
        _CACHE[name] = (resp.get_json(), len(resp.data), elapsed_ms)
    return _CACHE[name]


# ---------------------------------------------------------------------------
# P-6 — include_plots
# ---------------------------------------------------------------------------

def test_varsayilan_yanit_tam_figur_seti_tasir(client):
    """Alan verilmezse davranış eskisi: 10 figür anahtarının tümü üretilir."""
    body, _, _ = _response(client, 'default')
    assert isinstance(body['plots'], dict)
    assert set(body['plots'].keys()) == EXPECTED_PLOT_KEYS
    # En azından ana kesit figürü gerçekten üretilmiş olmalı (None değil).
    assert body['plots']['motor'] is not None
    assert 'slim' not in body


def test_include_plots_false_figur_uretmez_sayilari_degistirmez(client):
    """P-6: figürler atlanır, plots açıkça null; SAYISAL sonuç birebir kalır."""
    default_body, _, _ = _response(client, 'default')
    off_body, _, _ = _response(client, 'plots_off',
                               payload_extra={'include_plots': False})
    # 'plots' anahtarı DURUR ve açıkça null'dur — "figür var ama boş"
    # izlenimi veren None doldurulmuş sözlük yasak.
    assert 'plots' in off_body
    assert off_body['plots'] is None
    # Figür dışındaki sözleşme aynıdır: aynı üst seviye anahtar kümesi.
    assert set(off_body.keys()) == set(default_body.keys())
    # Sayısal motor sonucu değişmez (davranış-uyumluluk sözleşmesi).
    for key, val in default_body['motor'].items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            assert off_body['motor'][key] == pytest.approx(
                val, rel=1e-9, abs=1e-12), f'motor.{key} değişti'
    # Yörünge VERİSİ figür değildir, hesaplanmaya devam eder (P-6 yalnız
    # sunumu atlar; ham seriler ancak slim=1 ile düşer).
    assert 'trajectory' in off_body['trajectory']


def test_include_plots_false_yaniti_kucultur(client):
    """Figürsüz yanıt ölçülür biçimde küçüktür (ölçülen: −%48)."""
    _, default_size, default_ms = _response(client, 'default')
    _, off_size, off_ms = _response(client, 'plots_off',
                                    payload_extra={'include_plots': False})
    assert off_size < default_size * 0.75, (
        f'figürsüz yanıt beklenen kadar küçülmedi: '
        f'{off_size} / {default_size} bayt')
    # Süre bilgi amaçlı raporlanır; duvar saati florası yüzünden sert süre
    # eşiği konmaz (boyut sözleşmesi kararlı bekçidir).
    print(f'\n[ölçüm] /calculate varsayılan {default_ms:.0f} ms '
          f'{default_size/1024:.0f} KB; include_plots=false {off_ms:.0f} ms '
          f'{off_size/1024:.0f} KB')


# ---------------------------------------------------------------------------
# P-5 — ?slim=1
# ---------------------------------------------------------------------------

def test_slim_semasi_kilitli(client):
    """slim=1: iki ham alan düşer, düşen alanlar beyan edilir, özet kalır."""
    default_body, default_size, _ = _response(client, 'default')
    slim_body, slim_size, _ = _response(client, 'slim', query='?slim=1')

    assert slim_body.get('slim') is True
    slim_traj = slim_body['trajectory']
    default_traj = default_body['trajectory']

    # Denetimin öncülü hâlâ geçerli olmalı: varsayılan yanıt ham serileri
    # ve kopya bloğu TAŞIR (taşımıyorsa bu test güncellenmeli, P-5 bitmiş).
    assert SLIM_OMITTED_TRAJECTORY_FIELDS <= set(default_traj.keys())

    # Düşürülenler gerçekten yok; beyan alanı tam olarak onları sayıyor.
    assert not (SLIM_OMITTED_TRAJECTORY_FIELDS & set(slim_traj.keys()))
    assert set(slim_traj['omitted_fields'].keys()) == \
        SLIM_OMITTED_TRAJECTORY_FIELDS

    # Yörünge ÖZETİ (apogee, evreler, kurtarma, uyarılar...) yerinde:
    # düşürülen iki alan + beyan dışında şema birebir aynı.
    assert (set(slim_traj.keys()) - {'omitted_fields'}
            == set(default_traj.keys()) - SLIM_OMITTED_TRAJECTORY_FIELDS)

    assert slim_size < default_size, 'slim yanıtı küçültmüyor'


def test_slim_ve_figursuz_birlikte(client):
    """slim=1 + include_plots=false birleşimi en küçük yanıtı verir (−%72)."""
    _, default_size, _ = _response(client, 'default')
    _, both_size, _ = _response(client, 'both', query='?slim=1',
                                payload_extra={'include_plots': False})
    assert both_size < default_size * 0.6, (
        f'birleşik küçülme beklenenin altında: {both_size}/{default_size}')


def test_slim_verilmezse_varsayilan_degismez(client):
    """slim parametresi yokken yanıtta ne 'slim' ne 'omitted_fields' olur."""
    body, _, _ = _response(client, 'default')
    assert 'slim' not in body
    assert 'omitted_fields' not in body['trajectory']


# ---------------------------------------------------------------------------
# Konsol gürültüsü — /calculate_liquid stdout tekrarları
# ---------------------------------------------------------------------------

def test_calculate_liquid_konsol_tekrari_kesilir(client, capsys):
    """Motor stdout'unda birebir tekrar kalmaz; bilgi ve sayım beyanı kalır."""
    resp = client.post('/calculate_liquid', json=LIQUID_PAYLOAD)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    out_lines = capsys.readouterr().out.splitlines()

    # 1) Gürültü kaynağı satırlar (ölçülen: 27x / 23x / 4x tekrar) artık
    #    en fazla BİRER kez geçer.
    engine_noise = [l for l in out_lines
                    if 'NASA Validation' in l or l.startswith('Effective C*')]
    tekrarlar = {l: n for l, n in
                 collections.Counter(engine_noise).items() if n > 1}
    assert not tekrarlar, f'motor satırları hâlâ tekrarlıyor: {tekrarlar}'

    # 2) Bilgi SİLİNMEMİŞ: her iki satır ailesinin ilk örneği duruyor.
    assert any('NASA Validation' in l for l in out_lines)
    assert any(l.startswith('Effective C*') for l in out_lines)

    # 3) Bastırılan tekrar sayısı açıkça beyan edilir (sessiz kesinti yok).
    ozet = [l for l in out_lines if 'calculate_liquid.stdout_dedup' in l]
    assert len(ozet) == 1, out_lines[-5:]
    m = re.search(r'total=(\d+) unique=(\d+) suppressed=(\d+)', ozet[0])
    assert m, ozet[0]
    total, unique, suppressed = map(int, m.groups())
    assert total == unique + suppressed
    assert suppressed > 0, (
        'bu yük ölçümde ~200 tekrar üretiyordu; hiç bastırma olmaması '
        'süzgecin devreden çıktığını gösterir')


def test_dedup_suzgeci_kapsam_disini_degistirmez():
    """Süzgeç yalnız kendi iş parçacığının kapsamında dedup yapar.

    Kapsam yokken yazılanlar (ve eşzamanlı BAŞKA iş parçacıkları) olduğu
    gibi geçer — contextlib.redirect_stdout'un süreç-genel davranışına karşı
    bilinçli tasarım (gerekçe: app.py::_ThreadLocalLineDedup docstring).
    """
    import io
    import threading
    from hrma.app import _ThreadLocalLineDedup

    sink = io.StringIO()
    stream = _ThreadLocalLineDedup(sink)

    # Kapsam yok: tekrarlar aynen geçer.
    stream.write('ayni satir\n')
    stream.write('ayni satir\n')
    assert sink.getvalue() == 'ayni satir\nayni satir\n'

    # Bu iş parçacığında kapsam açıkken, DİĞER iş parçacığı süzülmez.
    sink2 = io.StringIO()
    stream2 = _ThreadLocalLineDedup(sink2)
    stream2.begin_scope()
    try:
        stream2.write('tekrar\n')
        stream2.write('tekrar\n')  # bu iş parçacığında bastırılır

        def diger():
            stream2.write('tekrar\n')
            stream2.write('tekrar\n')  # kapsamsız iş parçacığı: aynen geçer

        t = threading.Thread(target=diger)
        t.start()
        t.join()
    finally:
        state = stream2.end_scope()
    assert state['seen']['tekrar'] == 2
    # 1 (kapsamlı ilk görülüş) + 2 (kapsamsız iş parçacığı) = 3 satır
    assert sink2.getvalue().count('tekrar\n') == 3

    # Satır sonu gelmemiş kuyruk parçası kapanışta kaybolmaz.
    sink3 = io.StringIO()
    stream3 = _ThreadLocalLineDedup(sink3)
    stream3.begin_scope()
    stream3.write('yarim satir')
    stream3.end_scope()
    assert sink3.getvalue() == 'yarim satir'
