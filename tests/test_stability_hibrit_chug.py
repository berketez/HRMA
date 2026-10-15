"""Hibrit chug çevrimi bağlaması + form kapıları (v2.6.27, F2b hibrit ayağı).

Parti 27'de sıvı motora bağlanan gerçek chug çevriminin (hrma.stability.chug)
hibrit İKİZİ burada kilitlenir. Bugünkü CI dersi (kanal var kapı yok sınıfı)
üç katmanda birden bağlanır:

  (1) MOTOR: chug_loop combustion_stability bloğunda; J oran kuralının KENDİ
      ölçtüğü orandır (acoustic_modes.stability_report.chug — tek kaynak),
      τ enjektör devre çözümünün kendi jetinden türeyen ikincil parçalanma
      süresi (sıvıdaki desen, AYNI sabit ithal edilir), τ_c çekirdeğin
      chamber_time_constant'ı. Atalet kapıları (feed_line_length_m +
      feed_line_inner_diameter_mm) verilirse çevrim ikinci mertebe forma
      geçer; verilmezse ataletsiz koşar ve BEYAN eder.
  (2) FORM: advanced.html'de iki kapı (optNum sözleşmesi: boş alan payload'a
      girmez) + yapısal tarama (motora ulaşan her anahtarın form ucunda
      karşılığı — iki yönlü eşikli).
  (3) UÇ: /calculate yanıtında blok yayımlanır. DÜRÜST AÇIK: app.py'nin
      /calculate hibrit kurucusu feed_line_* anahtarlarını HENÜZ geçirmiyor
      (hibritte overrides kanalı yok, alanlar tek tek geçirilir; app.py bu
      iş kaleminin dosya kümesi DIŞINDA — A3 raporunda defter kalemi).
      İlgili uçtan uca bekçi kablo çekilene kadar AÇIK SKIP ile bekler ve
      kablo çekilince kendiliğinden devreye girer (yalan yeşil yok).
      ÖLÇÜLDÜ (27 Ağustos 2026, AST): kablo ÇEKİLMİŞ — ``/calculate``
      hibrit kurucusu ``feed_line_length_m`` ve
      ``feed_line_inner_diameter_mm`` anahtarlarını geçiriyor, uçtan uca
      bekçi KOŞUYOR. Kablonun yönü ``FEED_LINE_KABLOSU_TAKILI_BEKLENEN``
      ile DONDURULMUŞTUR: geri sökülürse bekçi sessizce skip'e düşmez,
      KIRMIZI olur (ÖH defter P14M4-05b'nin ikizi, Faz B-1 devri).

Mekanizma ayrımı (çift sayım yok): chug_loop oksitleyici besleme kuplajını
bağlar; yakıt buharlaşma gecikmesi (LFI, Karabeyoglu) AYRI blokta ayrı
kapsam etiketiyle durur — chug_loop.mechanism_scope bunu yazılı beyan eder.
"""

import ast
import copy
import math
import pathlib
import re
import warnings

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    FEED_LINE_INNER_DIAMETER_RANGE_MM,
    FEED_LINE_LENGTH_RANGE_M,
    HybridRocketEngine,
)
from hrma.stability.chamber import chamber_time_constant
from hrma.stability.chug import feed_inertance_time_constant
from tests.test_hybrid_input_wiring import BASE, HEADERS

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'
ENGINE_PY = REPO_ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py'
LIQUID_PY = REPO_ROOT / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'

#: Kalem 4'ün birebir kapsam beyanı (LFI ile çift sayım reddi).
MEKANIZMA_KAPSAMI = (
    'oxidizer feed-coupled chug; the fuel-vaporisation LFI '
    'mechanism is assessed separately in combustion_stability.lfi')


def oku(yol):
    return yol.read_text(encoding='utf-8')


def _kos(**degisiklik):
    """Tasarım noktası koşulmuş hibrit motor + sonuç (dalga6 deseni)."""
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def taban():
    """Atalet kapıları BOŞ koşu (formun bugünkü varsayılan hâli)."""
    return _kos()


@pytest.fixture(scope='module')
def ataletli():
    """Kapılar dolu: 1,5 m + 12 mm (sıvı bekçileriyle aynı örnek değerler)."""
    return _kos(feed_line_length_m=1.5, feed_line_inner_diameter_mm=12.0)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _yapraklar(dugum, yol='$'):
    out = {}
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            out.update(_yapraklar(v, f'{yol}.{k}'))
    elif isinstance(dugum, (list, tuple)):
        for i, v in enumerate(dugum):
            out.update(_yapraklar(v, f'{yol}[{i}]'))
    else:
        out[yol] = dugum
    return out


def _sayi_yollari(dugum, yol=''):
    """NOT_MODELLED beyan bloklarında boş olması gereken sayısal yapraklar."""
    bulunan = []
    if isinstance(dugum, bool):
        return bulunan
    if isinstance(dugum, (int, float)):
        bulunan.append(yol or '<kok>')
    elif isinstance(dugum, dict):
        for k, v in dugum.items():
            bulunan.extend(_sayi_yollari(v, f'{yol}.{k}' if yol else k))
    elif isinstance(dugum, (list, tuple)):
        for i, v in enumerate(dugum):
            bulunan.extend(_sayi_yollari(v, f'{yol}[{i}]'))
    return bulunan


# ===========================================================================
# 1. Motor: chug çevrimi bağlı ve çekirdekle bit-aynı
# ===========================================================================
def test_chug_loop_yayimlaniyor(taban):
    _, sonuc = taban
    blok = sonuc['combustion_stability']['chug_loop']
    assert blok['status'] == 'modelled', blok
    assert blok['model'] in ('lumped_capacitance_resistance_delay',
                             'lumped_inertance_capacitance_resistance_delay')
    assert blok['chamber_time_constant']['tau_c_s'] > 0
    assert blok['tau_source'].strip()
    assert blok['tau_c_source'].strip()
    # Hüküm disiplini: kapsam etiketi zorunlu, çıplak hüküm yok
    assert blok['verdict'] in ('stable', 'unstable', 'marginal')
    assert blok['verdict_scope'].startswith('feed-coupled chug')
    assert blok['verdict_basis'].strip()


def test_mekanizma_kapsami_lfi_cift_sayimini_reddediyor(taban):
    """Kalem 4: chug_loop, LFI'nin AYRI mekanizma olduğunu adıyla beyan eder."""
    _, sonuc = taban
    blok = sonuc['combustion_stability']['chug_loop']
    assert blok['mechanism_scope'] == MEKANIZMA_KAPSAMI
    assert 'feed line' in blok['mechanism_scope_basis']
    # LFI gerçekten ayrı blokta ve kendi kapsam etiketiyle duruyor
    lfi = sonuc['combustion_stability']['lfi']
    assert lfi['status'] == 'modelled'
    assert 'chug' not in (lfi.get('verdict_scope') or '')


def test_j_oran_kuralinin_kendi_olcumu_tek_kaynak(taban):
    """Çevrimin J'si, kuralın ölçtüğü oranın TA KENDİSİ (iki ayrı sayı yok)."""
    _, sonuc = taban
    kural = sonuc['acoustic_modes']['stability_report']['chug']
    blok = sonuc['combustion_stability']['chug_loop']
    assert kural['evaluated'] is True
    assert blok['dp_ratio_j'] == kural['injector_dp_ratio']
    assert 'acoustic_modes.stability_report.chug' in \
        blok['rule_vs_loop']['ratio_rule_source']


def test_tau_c_cekirdegin_dogrudan_cagrisiyla_bit_ayni(taban):
    """τ_c, çekirdeğe motorun YAYIMLADIĞI alanlarla gidilince aynı çıkar."""
    _, sonuc = taban
    blok = sonuc['combustion_stability']['chug_loop']
    beklenen = chamber_time_constant(
        l_star_m=float(sonuc['l_star_achieved']),
        c_star_m_s=float(sonuc['c_star']),
        gamma=float(sonuc['gamma']))
    assert blok['tau_c_s'] == beklenen['tau_c_s']
    assert blok['chamber_time_constant']['gamma_function_sq'] == \
        beklenen['gamma_function_sq']
    assert 'l_star_achieved' in blok['tau_c_source']


def test_tau_enjektor_cozumunden_ayni_sabitle(taban):
    """τ = T*·d_jet/v_jet·√(ρ_l/ρ_gaz) — sıvıdaki sabit İTHAL, kopya değil."""
    from hrma.engines.liquid_rocket_engine import DROPLET_BREAKUP_TIME_CONST
    motor, sonuc = taban
    inj = sonuc['injector_design']
    rho_gaz = (float(sonuc['chamber_pressure']) * 1e5
               / ((8314.462618 / float(sonuc['molecular_weight']))
                  * float(sonuc['chamber_temperature'])))
    beklenen = (DROPLET_BREAKUP_TIME_CONST
                * (float(inj['orifice_diameter_mm']) * 1e-3)
                / float(inj['injection_velocity_m_s'])
                * np.sqrt(float(motor._inj_rho_ox) / rho_gaz))
    blok = sonuc['combustion_stability']['chug_loop']
    assert blok['tau_s'] == pytest.approx(float(beklenen), rel=1e-12)
    assert 'not a second copy' in blok['tau_source']
    # Sabitin SAYISI motor dosyasına kopyalanmadı (parametre tutarlılığı):
    # hibrit kaynağında 'DROPLET_BREAKUP_TIME_CONST = <sayı>' tanımı yok,
    # yalnız import var.
    kaynak = oku(ENGINE_PY)
    assert 'DROPLET_BREAKUP_TIME_CONST' in kaynak
    assert not re.search(r'DROPLET_BREAKUP_TIME_CONST\s*=\s*[0-9]', kaynak)


def test_rule_vs_loop_olculuyor(taban):
    _, sonuc = taban
    rv = sonuc['combustion_stability']['chug_loop']['rule_vs_loop']
    assert rv['ratio_rule_status'] in ('OK', 'MARGINAL', 'AT_RISK')
    assert rv['agreement'] in ('agree', 'disagree')
    kural_guvenli = rv['ratio_rule_status'] in ('OK', 'MARGINAL')
    cevrim_kararli = rv['loop_verdict'] == 'stable'
    assert rv['agreement'] == ('agree' if kural_guvenli == cevrim_kararli
                               else 'disagree')


# ===========================================================================
# 2. Kapılar boş → ataletsiz + beyan (kalem 7a)
# ===========================================================================
def test_kapilar_bos_ataletsiz_ve_beyanli(taban):
    _, sonuc = taban
    blok = sonuc['combustion_stability']['chug_loop']
    assert blok['inertance_included'] is False
    assert blok['tau_f_s'] is None
    assert blok['feed_line'] is None
    assert 'NOT included' in blok['inertance_basis']
    assert 'inertance-free' in blok['verdict_scope']


def test_calculate_ucu_ataletsiz_beyanla_yayimliyor(istemci):
    """/calculate yanıtı chug_loop taşıyor; kapılar boşken ataletsiz beyan."""
    yanit = istemci.post('/calculate',
                         json=dict(BASE, include_plots=False),
                         headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    motor = yanit.get_json()['motor']
    blok = motor['combustion_stability']['chug_loop']
    assert blok['status'] == 'modelled'
    assert blok['inertance_included'] is False
    assert blok['mechanism_scope'] == MEKANIZMA_KAPSAMI


# ===========================================================================
# 3. Kapılar dolu → atalet devrede, yapraklar oynar (kalem 7b)
# ===========================================================================
def test_kapilar_dolu_atalet_devrede(taban, ataletli):
    _, bos = taban
    _, dolu = ataletli
    blok = dolu['combustion_stability']['chug_loop']
    assert blok['status'] == 'modelled'
    assert blok['inertance_included'] is True
    assert isinstance(blok['tau_f_s'], float) and blok['tau_f_s'] > 0
    assert blok['model'] == 'lumped_inertance_capacitance_resistance_delay'
    yanki = blok['feed_line']
    assert yanki['line_length_m'] == 1.5
    assert yanki['line_inner_diameter_mm'] == 12.0
    assert yanki['line_area_m2'] == pytest.approx(
        math.pi * 0.012 ** 2 / 4.0, rel=1e-12)
    # Debi OKSİTLEYİCİ debisi (hibritte hattan yalnız oksitleyici akar)
    assert yanki['mass_flow_kg_s'] == pytest.approx(
        float(dolu['mdot_ox']), rel=1e-12)
    # Yapraklar GERÇEKTEN oynadı (kapı süs değil)
    degisen = [
        p for p in (set(_yapraklar(bos['combustion_stability']['chug_loop']))
                    | set(_yapraklar(blok)))
        if _yapraklar(bos['combustion_stability']['chug_loop']).get(p)
        != _yapraklar(blok).get(p)]
    assert degisen, 'kapılar dolduruldu ama chug_loop yaprağı oynamadı'
    assert any('tau_f' in p or 'inertance' in p or 'feed_line' in p
               for p in degisen), degisen[:10]


def test_tau_f_cekirdekle_bit_ayni(ataletli):
    """τ_f = ℓ·ṁ/(2·A·ΔP) — çekirdeğe yayımlanan değerlerle gidilince aynı."""
    _, dolu = ataletli
    blok = dolu['combustion_stability']['chug_loop']
    beklenen = feed_inertance_time_constant(
        line_length_m=1.5,
        line_area_m2=math.pi * 0.012 ** 2 / 4.0,
        mass_flow_kg_s=float(dolu['mdot_ox']),
        dp_injector_Pa=float(
            dolu['injector_design']['injection_pressure_drop_bar']) * 1e5)
    assert blok['tau_f_s'] == beklenen


# ===========================================================================
# 4. Bant dışı / geçersiz girdi: sessiz kırpma yok, beyanlı düşüş (kalem 1)
# ===========================================================================
def test_bant_disi_girdi_beyanla_dusuyor():
    motor, sonuc = _kos(feed_line_length_m=999.0,
                        feed_line_inner_diameter_mm='abc')
    assert motor.feed_line_length_m is None
    assert motor.feed_line_inner_diameter_mm is None
    kayitlar = [k for k in motor._defaults_used if 'feed_line' in k]
    assert any('out_of_range' in k for k in kayitlar), kayitlar
    assert any('invalid' in k for k in kayitlar), kayitlar
    blok = sonuc['combustion_stability']['chug_loop']
    assert blok['inertance_included'] is False


def test_tek_kapi_yetmez_atalet_kurulmaz():
    """Uzunluk verilip çap verilmezse (ya da tersi) τ_f uydurulmaz."""
    _, sonuc = _kos(feed_line_length_m=1.5)
    assert sonuc['combustion_stability']['chug_loop'][
        'inertance_included'] is False


def test_bantlar_sivi_ile_birebir():
    """Sınır kopyası tek yerde: hibrit sabitleri sıvı bandıyla aynı sayılar."""
    assert FEED_LINE_LENGTH_RANGE_M == (0.05, 50.0)
    assert FEED_LINE_INNER_DIAMETER_RANGE_MM == (0.5, 500.0)
    sivi = oku(LIQUID_PY)
    assert re.search(r"_override_val\('feed_line_length_m',\s*0\.05,\s*50\.0",
                     sivi), 'sıvı bandı değişmiş — hibrit sabiti eskidi'
    assert re.search(r"'feed_line_diameter_mm',\s*0\.5,\s*500\.0", sivi), (
        'sıvı çap bandı değişmiş — hibrit sabiti eskidi')
    # Form min/max motor sınırlarıyla birebir
    html = oku(ADVANCED_HTML)
    uzunluk = re.search(r'<input[^>]*id="feed_line_length_m"[^>]*>', html)
    cap = re.search(r'<input[^>]*id="feed_line_inner_diameter_mm"[^>]*>',
                    html)
    assert uzunluk and 'min="0.05"' in uzunluk.group(0) \
        and 'max="50"' in uzunluk.group(0)
    assert cap and 'min="0.5"' in cap.group(0) and 'max="500"' in cap.group(0)


# ===========================================================================
# 5. Su koçu beyanı: güncellendi ama sözleşme KIRILMADI (kalem 7c)
# ===========================================================================
def test_su_kocu_beyani_guncel_ve_kirik_degil(taban):
    _, sonuc = taban
    kocu = sonuc['feed_water_hammer']
    assert kocu['status'] == 'NOT_MODELLED'
    assert 'no line diameter' in kocu['reason']
    assert set(kocu['required_inputs']) == {
        'feed_line_length_m', 'feed_line_inner_diameter_mm',
        'feed_line_wall_thickness_mm', 'valve_closure_time_ms'}
    assert not _sayi_yollari(kocu), _sayi_yollari(kocu)
    # Beyan artık chug_loop kanalını da adıyla anlatıyor (yalan kalmadı)
    assert 'chug_loop' in kocu['reason']


# ===========================================================================
# 6. Hüküm disiplini (kalem 7d)
# ===========================================================================
def _verdict_dugumleri(dugum, yol='$'):
    if isinstance(dugum, dict):
        if 'verdict' in dugum:
            yield yol, dugum
        for k, v in dugum.items():
            yield from _verdict_dugumleri(v, f'{yol}.{k}')
    elif isinstance(dugum, (list, tuple)):
        for i, v in enumerate(dugum):
            yield from _verdict_dugumleri(v, f'{yol}[{i}]')


def test_hukum_daima_kapsam_etiketli(taban, ataletli):
    for _, sonuc in (taban, ataletli):
        blok = sonuc['combustion_stability']['chug_loop']
        dugumler = list(_verdict_dugumleri(blok))
        assert dugumler, 'chug_loop hüküm taşımıyor'
        for yol, dugum in dugumler:
            assert str(dugum.get('verdict_scope') or '').strip(), (
                f'{yol}: çıplak hüküm (kapsam etiketi yok)')
            assert str(dugum.get('verdict_basis') or '').strip(), (
                f'{yol}: gerekçesiz hüküm')


def test_akustik_esik_yolunda_hukum_hala_yasak(taban):
    """Chug bağlaması eşik yoluna hüküm sızdırmadı (forbid_verdict_key)."""
    _, sonuc = taban
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    assert esik['status'] == 'modelled'
    assert not list(_verdict_dugumleri(esik)), (
        'akustik eşik yolunda verdict anahtarı türedi')


# ===========================================================================
# 7. Yapısal tarama: motora ulaşan her anahtarın form ucunda karşılığı
#    (kalem 6 — kanal var kapı yok sınıfının hibrit bekçisi)
# ===========================================================================
#: GEREKÇELİ istisna: sözlük tipli girdi tek input alanıyla temsil edilemez.
BILINCLI_ISTISNALAR = {
    # launch_site: resolve_launch_site() sözleşmeli SÖZLÜK ister
    # ({'elevation_m'} ya da {'latitude_deg','longitude_deg'}); skaler bir
    # form alanı bu sözleşmeyi taşıyamaz. Kanal API/saha seçici içindir.
    'launch_site',
}

#: BUGÜN ÖLÇÜLEN açık (gerekçesi ARAŞTIRILMADI — uydurma gerekçe yazılmaz;
#: A3 raporunda defter kalemi). İKİ YÖNLÜ EŞİK: bu küme BÜYÜYEMEZ (yeni
#: kapısız kanal = kırmızı) ve KÜÇÜLMEDEN buradan satır silinemez (kapı
#: açıldıysa satır da silinmeli, yoksa test kırmızı).
KAPISIZ_BILINEN = {
    # 'ambient_temp' — parti 33'te kapı AÇILDI (advanced.html + optNum;
    # kanal ölçümü: 233,15 K → 781 yaprak; bekçisi
    # tests/test_ambient_temp_kanali.py) ve satır kaldırıldı.
    'chamber_temperature',
    'gamma',
    'gas_constant',
    'thrust_coefficient',
}


def _calculate_isleyicisi():
    src = oku(APP_PY)
    bas = src.index("@app.route('/calculate', methods=['POST'])")
    son = src.index('@app.route', bas + 10)
    return src[bas:son]


def _istek_okumalari(dugum, istek_adi):
    """``<istek>.get('X')`` / ``<istek>['X']`` biçiminde okunan alan adları.

    Alıcı ifadesinin ``Name`` olması ŞART DEĞİL: ``(data or {}).get('X')``
    da sayılır (alıcı içinde istek adı geçiyorsa yeter). Bu gevşeklik
    ölçülmüş bir kusurdan doğdu — aşağıdaki ``_motora_ulasan_anahtarlar``
    künyesine bakın.
    """
    def alici_kullaniyor(n):
        return any(isinstance(x, ast.Name) and x.id == istek_adi
                   for x in ast.walk(n))

    adlar = set()
    for n in ast.walk(dugum):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'get' and n.args
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)
                and alici_kullaniyor(n.func.value)):
            adlar.add(n.args[0].value)
        if (isinstance(n, ast.Subscript)
                and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)
                and alici_kullaniyor(n.value)):
            adlar.add(n.slice.value)
    return adlar


def _motora_ulasan_anahtarlar():
    """/calculate içinde HybridRocketEngine(...) çağrısına giren data anahtarları.

    ÖH D15 (1 Eyl 2026) — TARAYICI ONARILDI. Eskisi çağrı METNİNDE
    ``data.get('X')`` deseni arıyordu; ``test_yapisal_tarama_gercekten_
    anahtar_goruyor`` negatif kontrolü tam bunun için yazılmıştı ("tarama
    köreldiyse burada kırılır") ve KIRILDI: ``chamber_pressure`` artık
    çağrıda görünmüyor.

    Alan ölü DEĞİL, körelen taramaydı. app.py çağrıdan ÖNCE
    ``chamber_pressure_input = _pc_varsayilan_kunyesi(data, ...)`` yapıyor
    (P7B1-02, sessiz 20 bar varsayılanını BEYAN etmek için) ve o yardımcı
    içinde okuma ``(data or {}).get('chamber_pressure')`` biçiminde —
    yani ne çağrı gövdesinde ne de düz ``data.get`` deseninde.

    Onarım desen genişletmek DEĞİL, bağı İZLEMEK: çağrı AST ile bulunur,
    her anahtar için (a) doğrudan okuma, (b) ``data``yı alan modül
    düzeyi bir yardımcıya yapılan çağrı, (c) aynı işlevdeki yerel atama
    zinciri sırayla çözülür. Beklenen adı listeye elle yazmak kusuru
    gizlerdi — negatif kontrolün varlık sebebi tam olarak budur.
    """
    agac = ast.parse(oku(APP_PY))
    modul_fonksiyonlari = {
        f.name: f for f in agac.body
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    isleyici = cagri = None
    for f in ast.walk(agac):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if f.name != 'calculate':
            continue
        for n in ast.walk(f):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == 'HybridRocketEngine'):
                isleyici, cagri = f, n
    assert cagri is not None, ('app.py içinde /calculate -> '
                              'HybridRocketEngine(...) çağrısı bulunamadı')

    def coz(dugum, derinlik=0):
        adlar = _istek_okumalari(dugum, 'data')
        if adlar or derinlik > 3:
            return adlar
        # (b) data'yı devralan modül düzeyi yardımcı
        for n in ast.walk(dugum):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in modul_fonksiyonlari):
                yardimci = modul_fonksiyonlari[n.func.id]
                parametreler = [a.arg for a in yardimci.args.args]
                for sira, arg in enumerate(n.args):
                    if (isinstance(arg, ast.Name) and arg.id == 'data'
                            and sira < len(parametreler)):
                        adlar |= _istek_okumalari(yardimci,
                                                  parametreler[sira])
        if adlar:
            return adlar
        # (b2) ÖH D32 app-api-uc a1 (OH-D31-13, 15 Eyl 2026) — TARAYICI
        # İKİNCİ KEZ ONARILDI (ana model, fix-35c-2). Negatif kontrol yine
        # kırıldı: ``of_ratio`` çağrıda ``of_ratio=_uc_yedegi('of_ratio')``
        # oldu; ``_uc_yedegi`` calculate() İÇİNDE tanımlı bir kapanış ve
        # ``data``yı gövdesinden okuyor, anahtar ise çağrıdaki DİZE
        # LİTERALİ. (b) yalnız modül düzeyi yardımcıyı izliyordu. Kural:
        # işleyicinin içinde tanımlı bir işlev hem ``data``ya hem o
        # konumdaki parametresine dokunuyorsa, o konuma verilen dize
        # literali okunan anahtardır. Beklenen adı listeye yazmak yerine
        # bağ izlenir (negatif kontrolün varlık sebebi).
        ic_fonksiyonlar = {
            f.name: f for f in ast.walk(isleyici)
            if isinstance(f, ast.FunctionDef) and f is not isleyici}
        for n in ast.walk(dugum):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ic_fonksiyonlar):
                continue
            ic = ic_fonksiyonlar[n.func.id]
            parametreler = [a.arg for a in ic.args.args]
            adlar_ic = {m.id for m in ast.walk(ic) if isinstance(m, ast.Name)}
            if 'data' not in adlar_ic:
                continue
            for sira, arg in enumerate(n.args):
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and sira < len(parametreler)
                        and parametreler[sira] in adlar_ic):
                    adlar.add(arg.value)
        if adlar:
            return adlar
        # (c) aynı işlevdeki yerel atama zinciri
        for n in ast.walk(dugum):
            if isinstance(n, ast.Name) and n.id != 'data':
                for a in ast.walk(isleyici):
                    if isinstance(a, ast.Assign) and any(
                            isinstance(t, ast.Name) and t.id == n.id
                            for t in a.targets):
                        adlar |= coz(a.value, derinlik + 1)
        return adlar

    bulunan = set()
    for kw in cagri.keywords:
        bulunan |= coz(kw.value)
    return bulunan


def _form_ucunda_var(anahtar, html):
    """id, toplayıcı ataması ya da nesne-literal anahtarı olarak var mı?"""
    return bool(
        re.search(r'\bid="%s"' % re.escape(anahtar), html)
        or re.search(r'\bdata\.%s\s*=' % re.escape(anahtar), html)
        or re.search(r'(?m)^\s*%s\s*:' % re.escape(anahtar), html))


def test_motora_ulasan_her_anahtarin_form_ucunda_karsiligi_var():
    html = oku(ADVANCED_HTML)
    anahtarlar = _motora_ulasan_anahtarlar()
    kapisiz = {a for a in anahtarlar
               if not _form_ucunda_var(a, html)} - BILINCLI_ISTISNALAR
    assert kapisiz == KAPISIZ_BILINEN, (
        'Kapısız kanal kümesi değişti. Yeni açık: %s — kapı ekleyin ya da '
        'GEREKÇESİYLE istisnaya yazın. Kapanan: %s — KAPISIZ_BILINEN '
        'satırını silin.' % (sorted(kapisiz - KAPISIZ_BILINEN),
                             sorted(KAPISIZ_BILINEN - kapisiz)))


def test_yapisal_tarama_gercekten_anahtar_goruyor():
    """Negatif kontrol: tarama köreldiyse (regex çürüdüyse) burada kırılır."""
    anahtarlar = _motora_ulasan_anahtarlar()
    assert {'thrust', 'burn_time', 'of_ratio', 'chamber_pressure',
            'fuel_type', 'oxidizer_type'} <= anahtarlar, anahtarlar
    assert len(anahtarlar) > 20


def test_bilincli_istisna_hala_motora_ulasiyor():
    olu = BILINCLI_ISTISNALAR - _motora_ulasan_anahtarlar()
    assert not olu, ('istisna listesinde app.py\'nin artık motor çağrısına '
                     'geçirmediği anahtar var: %s' % sorted(olu))


def test_yeni_kapilar_form_ve_toplayicida():
    """İki kapı da id + optNum kablosuyla duruyor; boş varsayılanlı."""
    html = oku(ADVANCED_HTML)
    for alan in ('feed_line_length_m', 'feed_line_inner_diameter_mm'):
        m = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(alan), html)
        assert m, f'{alan} alanı advanced.html\'de yok'
        assert 'value=""' in m.group(0), (
            f'{alan} boş varsayılanla durmalı (sayfa sayı dayatmaz): '
            f'{m.group(0)}')
        assert f"optNum('{alan}')" in html, (
            f'{alan} toplayıcıya (optNum) bağlanmamış')
    # Motor tarafında okuma kanalı gerçekten var (mutasyon bekçisinin çifti)
    kaynak = oku(ENGINE_PY)
    assert re.search(
        r'_resolve_feed_line_length\(\s*feed_line_length_m\s*\)', kaynak), (
        'motor feed_line_length_m kurucu girdisini çözümlemiyor')
    assert re.search(
        r'_resolve_feed_line_inner_diameter\('
        r'\s*feed_line_inner_diameter_mm\s*\)', kaynak), (
        'motor feed_line_inner_diameter_mm kurucu girdisini çözümlemiyor')


def test_stability_panel_include_analiz_merkezinin_altinda():
    """A1'in paneli çekirdekten SONRA yüklenir (kayıt sırası sözleşmesi)."""
    html = oku(ADVANCED_HTML)
    merkez = html.index('/static/js/analysis_center.js')
    panel = html.index('/static/js/panels/stability_panel.js')
    assert panel > merkez


# ===========================================================================
# 8. Uçtan uca /calculate — kablo çekilince kendiliğinden devreye girer
# ===========================================================================
def _rota_dekoratoru(dugum, yol):
    """``@app.route('<yol>', methods=[...])`` mi?"""
    return (isinstance(dugum, ast.Call)
            and isinstance(dugum.func, ast.Attribute)
            and dugum.func.attr == 'route'
            and dugum.args
            and isinstance(dugum.args[0], ast.Constant)
            and dugum.args[0].value == yol)


def _hibrit_kurucu_anahtarlari():
    """``/calculate``in ``HybridRocketEngine(...)`` çağrısının ANAHTAR adları.

    ÖLÇÜLEN KUSUR (ÖH defter P14M4-05b — bu dosyadaki :501 yükleminin BİREBİR
    İKİZİ, Faz B-1 devri): aşağıdaki dürüst skip eskiden ürün KAYNAK METNİNDE
    alt dizge arıyordu (``'feed_line_length_m' not in _calculate_isleyicisi()``).
    Alt dizge anahtarı bir YORUM SATIRINDA da bulur; kablo ile onu anlatan
    yorum birlikte sökülünce yüklem sessizce yön değiştirir, bekçi skip'e
    düşer ve süit hiçbir şey söylemeden yeşil kalır (P14 ölçümü: 9.250 testte
    tek kırmızı yok, sayaç 1-skipped'te sabit).

    Yeni yüklem YAPIya bakar: ``ast.Call`` -> ``keyword.arg``. Yorum artık
    yüklemi besleyemez. Desen ``tests/test_enjektor_sozlesme_borclari.py``de
    (B18 adımı) kuruldu, buraya kopyalanmıştır.

    DİKKAT: bu yardımcı ``_motora_ulasan_anahtarlar()``ın YERİNE GEÇMEZ. O,
    ``data.get('...')`` okumalarını sayar ve ``KAPISIZ_BILINEN`` iki yönlü
    eşiğini besler (tescilli sağlıklı desen — dokunulmaz); bu ise kurucuya
    giden kwarg ADlarını verir.
    """
    kaynak = oku(APP_PY)
    agac = ast.parse(kaynak, filename=str(APP_PY))
    for dugum in ast.walk(agac):
        if not (isinstance(dugum, ast.FunctionDef)
                and any(_rota_dekoratoru(d, '/calculate')
                        for d in dugum.decorator_list)):
            continue
        for ic in ast.walk(dugum):
            if (isinstance(ic, ast.Call) and isinstance(ic.func, ast.Name)
                    and ic.func.id == 'HybridRocketEngine'):
                return {k.arg for k in ic.keywords if k.arg}
    raise AssertionError(
        "app.py'de /calculate işleyicisinin HybridRocketEngine(...) çağrısı "
        'bulunamadı — bu bekçinin çapası kaymış, önce çağrıyı bul.')


#: İZLENEN KAPILAR — motorun atalet (ikinci mertebe) formuna geçmesi bu iki
#: kurucu anahtarına bağlıdır.
FEED_LINE_KAPILARI = ('feed_line_length_m', 'feed_line_inner_diameter_mm')

#: KABLONUN BUGÜNKÜ DURUMU — ÖLÇÜLDÜ (27 Ağustos 2026, AST): ``/calculate``
#: hibrit kurucusunun 39 kwarg'ı arasında iki kapı da VAR.
#:
#: Bu sabit yönü DONDURUR. Aşağıdaki uçtan uca bekçi "dürüst skip" desenini
#: kullanır; skip tek başına bırakılırsa kablonun SÖKÜLMESİ süitte hiçbir
#: kırmızı üretmez (yalnız sayaç 1-skipped'e kayar, dışarıdan görünmez —
#: P14M4-05b'nin ölçtüğü tam mekanizma). Sökme bilerek yapıldıysa bu satır
#: güncellenir ve gerekçesi yazılır.
FEED_LINE_KABLOSU_TAKILI_BEKLENEN = True


def test_feed_line_kablo_YONU_dondurulmus():
    """Kablonun varlığı bir ÖLÇÜMdür; sessizce yön değiştiremez.

    Yüklem app.py'nin YAPISINA bakar (``ast.Call`` -> ``keyword.arg``),
    kaynak METNİNE değil: bir yorum satırı kabloyu var gösteremez.
    """
    anahtarlar = _hibrit_kurucu_anahtarlari()
    takili = {a: (a in anahtarlar) for a in FEED_LINE_KAPILARI}
    assert all(takili.values()) is FEED_LINE_KABLOSU_TAKILI_BEKLENEN, (
        f'/calculate hibrit kurucusundaki besleme hattı kablosu beklenen '
        f'yönde değil: {takili} (beklenen hepsi='
        f'{FEED_LINE_KABLOSU_TAKILI_BEKLENEN}). Bu bir DAVRANIŞ '
        'değişikliğidir: kullanıcının hat uzunluğu/çapı motora '
        f'{"artık ulaşmıyor" if FEED_LINE_KABLOSU_TAKILI_BEKLENEN else "artık ulaşıyor"}'
        ' ve chug çevrimi mertebe değiştiriyor. Bilerek yapıldıysa '
        'FEED_LINE_KABLOSU_TAKILI_BEKLENEN güncellenir ve gerekçesi yazılır.')


def test_kablo_yuklemi_yorumla_beslenemez():
    """Negatif kontrol: yüklem AST'ye bakıyor, alt dizgeye değil.

    ÖLÇÜLEN KUSUR (P14M4-05b): eski yüklem işleyicinin kaynak METNİNDE
    ``'feed_line_length_m'`` alt dizgesini arıyordu; anahtarı ANAN bir yorum
    satırı da bu aramayı geçiyordu. Burada iki yüklem AYNI kaynak üzerinde
    karşılaştırılır: AST yüklemi yalnız gerçek kwarg'ları görmeli.
    """
    metin_yuklemi = 'feed_line_length_m' in _calculate_isleyicisi()
    ast_yuklemi = 'feed_line_length_m' in _hibrit_kurucu_anahtarlari()
    assert metin_yuklemi and ast_yuklemi, (
        f'bugünkü ölçüm: metin={metin_yuklemi}, AST={ast_yuklemi} — ikisi de '
        'doğru olmalıydı (kablo çekili)')
    # Yorumla beslenme denemesi: kwarg'ı SÖKÜP adını yalnız yoruma bırakan
    # bir kaynakta metin yüklemi hâlâ True, AST yüklemi False olmalıdır.
    sahte = ('@app.route(\'/calculate\', methods=[\'POST\'])\n'
             'def calculate():\n'
             '    # feed_line_length_m kablosu geçici olarak söküldü\n'
             '    return HybridRocketEngine(thrust=1.0)\n')
    agac = ast.parse(sahte)
    kwarglar = set()
    for dugum in ast.walk(agac):
        if (isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Name)
                and dugum.func.id == 'HybridRocketEngine'):
            kwarglar = {k.arg for k in dugum.keywords if k.arg}
    assert 'feed_line_length_m' in sahte           # metin yüklemi kanardı
    assert 'feed_line_length_m' not in kwarglar, (
        'AST yüklemi de yoruma kandı — bu bekçi kendini silahsızlandırmış')


def test_kapilar_calculate_ucundan_geciyor(istemci):
    """Dolu kapılar /calculate üzerinden çevrimi ikinci mertebeye geçirmeli.

    DÜRÜST SKIP: kablo yoksa bu bekçi kendiliğinden devreye girmez. Skip
    koşulu app.py'nin YAPISINA bakar (``ast.Call`` -> ``keyword.arg``),
    kaynak metnine değil — bir yorum satırı yüklemi besleyemez (P14M4-05b).
    Yön ayrıca ``test_feed_line_kablo_YONU_dondurulmus`` ile kilitlidir, yani
    skip'in unutulması imkânsızdır.
    """
    if 'feed_line_length_m' not in _hibrit_kurucu_anahtarlari():
        pytest.skip(
            'app.py /calculate hibrit kurucusu feed_line_length_m/'
            'feed_line_inner_diameter_mm anahtarlarını geçirmiyor — '
            'defter kalemi (A3, 2026-08-17). Kablo: HybridRocketEngine('
            "..., feed_line_length_m=data.get('feed_line_length_m'), "
            "feed_line_inner_diameter_mm="
            "data.get('feed_line_inner_diameter_mm'))")
    yuk = dict(copy.deepcopy(BASE), include_plots=False,
               feed_line_length_m=1.5, feed_line_inner_diameter_mm=12.0)
    yanit = istemci.post('/calculate', json=yuk, headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    blok = yanit.get_json()['motor']['combustion_stability']['chug_loop']
    assert blok['inertance_included'] is True
    assert isinstance(blok['tau_f_s'], float) and blok['tau_f_s'] > 0
