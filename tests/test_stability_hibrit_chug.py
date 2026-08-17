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

Mekanizma ayrımı (çift sayım yok): chug_loop oksitleyici besleme kuplajını
bağlar; yakıt buharlaşma gecikmesi (LFI, Karabeyoglu) AYRI blokta ayrı
kapsam etiketiyle durur — chug_loop.mechanism_scope bunu yazılı beyan eder.
"""

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
    'ambient_temp',
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


def _motora_ulasan_anahtarlar():
    """/calculate içinde HybridRocketEngine(...) çağrısına giren data anahtarları."""
    isleyici = _calculate_isleyicisi()
    bas = isleyici.index('HybridRocketEngine(')
    i = isleyici.index('(', bas)
    derinlik = 0
    son = i
    for j in range(i, len(isleyici)):
        if isleyici[j] == '(':
            derinlik += 1
        elif isleyici[j] == ')':
            derinlik -= 1
            if derinlik == 0:
                son = j
                break
    govde = isleyici[i:son + 1]
    return set(re.findall(r"data\.get\(\s*'([A-Za-z_0-9]+)'", govde))


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
def test_kapilar_calculate_ucundan_geciyor(istemci):
    """Dolu kapılar /calculate üzerinden çevrimi ikinci mertebeye geçirmeli.

    DÜRÜST SKIP: app.py /calculate hibrit kurucusu feed_line_* anahtarlarını
    henüz geçirmiyor (bu iş kaleminin dosya kümesi app.py'yi kapsamıyordu;
    A3 raporunda defter kalemi + tek satırlık kablo tarifi). Kablo çekilince
    bu bekçi otomatik devreye girer — skip koşulu app.py kaynağına bakar,
    hafızaya değil.
    """
    if 'feed_line_length_m' not in _calculate_isleyicisi():
        pytest.skip(
            'app.py /calculate hibrit kurucusu feed_line_length_m/'
            'feed_line_inner_diameter_mm anahtarlarını henüz geçirmiyor — '
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
