# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · kulvar `sablonlar` · aşama 3 — onarım bekçileri.

Her test TEK bir kusuru görür ve o kusur geri konduğunda KIRMIZI olur
(ters-mutasyon kanıtı: `docs/scofield/raw/OH/D15/sablonlar/a3/mutasyon.json`).
Ölçümler: aynı dizindeki `once.json` (a2 kapanışının ağacı) ve `sonra.json`.

İki tür bekçi var:

  * ONARIM BEKÇİSİ — bu aşamada onarılan kusuru gören test.
  * TABAN BEKÇİSİ — ölçümle ÇÜRÜTÜLEN (yani daha önce kapanmış) kalemin
    kapalı hâlini kilitleyen test. Kalem bir daha sessizce geri gelemez.

Saf JS yardımcıları node ile GERÇEKTEN koşturulur — metin sınamak yetmez.
node yoksa o testler atlanır.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLONLAR = KOK / 'hrma' / 'templates'
ADVANCED = SABLONLAR / 'advanced.html'
LIQUID = SABLONLAR / 'liquid.html'
FORMULAS = SABLONLAR / 'formulas.html'
LAUNCH_SITE = SABLONLAR / 'launch_site.html'
APP_PY = KOK / 'hrma' / 'app.py'
JSDIR = KOK / 'hrma' / 'static' / 'js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node yürütülebiliri yok; saf JS yardımcıları koşturulamıyor')


# --------------------------------------------------------------------------
# Ortak yardımcılar
# --------------------------------------------------------------------------
def _blok(src, imza_re):
    """imza ile başlayan bloğu süslü parantez eşleyerek çıkarır."""
    m = re.search(imza_re, src)
    assert m, 'blok bulunamadı: %s' % imza_re
    i = src.index('{', m.end() - 1)
    d = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[m.start():j + 1]
    raise AssertionError('blok kapanmadı: %s' % imza_re)


def _yorumsuz(src):
    """// ve /* */ yorumlarını atar — bekçi yorum metnine kanmamalı."""
    src = re.sub(r'/\*[\s\S]*?\*/', ' ', src)
    return re.sub(r'(?m)^\s*//.*$', ' ', src)


def _node(kod):
    # Betik argv ile DEĞİL stdin ile geçilir (repo sözleşmesi:
    # tests/test_node_cagri_sozlesmesi.py — Linux MAX_ARG_STRLEN tavanı).
    p = subprocess.run([NODE, '--input-type=commonjs'], input=kod,
                       capture_output=True, text=True, timeout=120)
    return p


@pytest.fixture(scope='module')
def advanced_src():
    return ADVANCED.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def liquid_src():
    return LIQUID.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def formulas_src():
    return FORMULAS.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def istemci():
    import contextlib
    import io
    import os
    import tempfile
    os.environ.setdefault(
        'HRMA_USER_DATA_DIR',
        os.path.join(tempfile.gettempdir(), 'hrma-bekci-d15-a3'))
    os.makedirs(os.environ['HRMA_USER_DATA_DIR'], exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, yuk):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=yuk)
    return r.status_code, r.get_json()


# --------------------------------------------------------------------------
# P12bB3-12 — parametrik taramanın dürüstlük alanları
# --------------------------------------------------------------------------
DURUSTLUK_ALANLARI = ('points_requested', 'points_succeeded', 'points_failed',
                      'failed_points', 'warning')


def test_b3_12_parametrik_durustluk_alanlari_okunuyor(advanced_src):
    """Sunucunun beş dürüstlük alanının HEPSİ şablonda okunmalı.

    ÖLÇÜLDÜ (once.json): şablon bunların HİÇBİRİNİ okumuyordu; sunucu
    "1 of 10 sweep points could not be computed" derken ekranda yeşil
    "completed successfully" yazıyordu.
    """
    g = _yorumsuz(_blok(advanced_src,
                        r'async function runParametricAnalysis\s*\('))
    eksik = [a for a in DURUSTLUK_ALANLARI
             if not re.search(r'results\.%s\b' % a, g)]
    assert not eksik, 'okunmayan dürüstlük alanı: %s' % eksik


def test_b3_12_basari_mesaji_dusen_nokta_sayisina_bagli(advanced_src):
    """"completed successfully" koşulsuz basılamaz — düşen nokta varsa hayır."""
    g = _yorumsuz(_blok(advanced_src,
                        r'async function runParametricAnalysis\s*\('))
    i = g.index('parametricAnalysisCompletedSuccessfully')
    yakin = g[max(0, i - 500):i]
    # Başarı mesajı, düşen-nokta hükmünün ELSE dalında olmalı.
    assert re.search(r'if\s*\(\s*dusen\s*>\s*0\s*\)', yakin), \
        'başarı mesajı düşen nokta sayısına bağlanmamış'
    assert re.search(r'\}\s*else\s*\{', yakin), \
        'başarı mesajı koşulsuz basılıyor (else dalında değil)'
    assert 'parametricAnalysisPartial' in yakin, \
        'kısmi tarama için ayrı (sayılı) mesaj yok'


def test_b3_12_sunucu_dusen_noktayi_hala_yayimliyor(istemci):
    """Bekçinin ölçtüğü kanal canlı: uç beş alanı gerçekten döndürüyor."""
    d, y = _post(istemci, '/parametric-analysis', {
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
        'param_type': 'of_ratio', 'param_start': 0.0, 'param_end': 12.0,
        'param_steps': 10})
    assert d == 200 and y.get('status') == 'success'
    assert y.get('points_failed', 0) >= 1, \
        'ölçüm senaryosu artık düşen nokta üretmiyor — bekçi kör kaldı'
    assert y.get('points_requested') == 10
    assert y.get('warning')


# --------------------------------------------------------------------------
# P12bB3-13 — CEA doğrulamasında korumasız .toFixed()
# --------------------------------------------------------------------------
def test_b3_13_olu_cea_sarmali_geri_gelmedi(advanced_src):
    """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11).

    ESKİ SÖZLEŞME: ``validateComposition()`` gövdesindeki her
    ``props.X.toFixed()`` çağrısının bir ``isFinite`` kapısının ardında
    olduğu, sunucunun üç beyanının (``*_note`` / ``*_method``) okunduğu ve
    biçimleyicinin gerçek (null'lu) yanıtla fırlatmadığı ölçülüyordu. Üç
    bekçi de ölü fonksiyonun sayfada DURMASINI şart koşuyordu.

    ÖLÇÜLDÜ (raw/OH/D33/arayuz-panel/a1/once.json · M2): fonksiyonun tek
    çağıranı OH-D31-05'te sökülen ``#custom_fuel_config`` panelinin
    düğmesiydi; ``#composition_rows`` sorgusu boş dönüyordu, yani biçimleyici
    ürün yolundan HİÇ çağrılamıyordu. Sarmal D33'te silindi.

    YENİ SÖZLEŞME: sarmal geri gelmez. Kalemin ÜRÜN ayağı —
    ``/api/validate-fuel`` ucunun hâlâ null yayımladığı — aşağıdaki
    ``test_b3_13_uc_hala_null_yayimliyor`` ile DOKUNULMADAN durur.
    """
    kod = re.sub(r'<!--.*?-->', '', advanced_src, flags=re.S)
    assert 'function validateComposition' not in kod, (
        'erişilemez CEA sarmalı geri geldi (OH-D32-11)')
    assert 'ceaSatir' not in kod, 'ölü biçimleyici geri geldi'


def test_b3_13_uc_hala_null_yayimliyor(istemci):
    """Bekçinin ölçtüğü kanal canlı: geçerli formülde üç alan hâlâ null."""
    d, y = _post(istemci, '/api/validate-fuel',
                 {'composition': [{'formula': 'C4H6', 'percentage': 100}]})
    assert d == 200 and y.get('status') == 'success'
    props = y.get('mixture_properties') or {}
    null_olanlar = [k for k in ('density', 'heat_of_formation',
                                'specific_heat') if props.get(k) is None]
    assert null_olanlar, \
        'uç artık null döndürmüyor — bekçi kör kaldı, senaryo yenilenmeli'
    assert isinstance(props.get('molecular_weight'), (int, float))


# --------------------------------------------------------------------------
# P12bB3-15 — pintle dış çapı hayalet alandan okunuyordu
# --------------------------------------------------------------------------
def test_b3_15_pintle_dali_outer_diameter_uretiyor(advanced_src):
    """Okunan her id üretilmeli: pintle dalı `#outer_diameter` basmalı.

    ÖH D32 · arayuz-panel a2 (OH-D31-14): okuma artık `enjAta('outer_diameter')`
    kapanışından geçiyor (`numById` -> boş alanın anahtarı gövdeye KONMAZ).
    Alan HÂLÂ okunuyor — değişen tek şey okumanın yazılışı. İddia iki yazımı
    da sayar; "hiç okunmuyor" hâli hâlâ KIRMIZI verir.
    """
    okuma = (len(re.findall(r"getElementById\('outer_diameter'\)", advanced_src))
             + len(re.findall(r"enjAta\('outer_diameter'", advanced_src)))
    assert okuma >= 1, 'okuma kayboldu — senaryo değişti'
    tanim = len(re.findall(r'\bid="outer_diameter"', advanced_src))
    assert tanim >= 1, 'sayfa `#outer_diameter` alanını hâlâ üretmiyor'
    pintle = advanced_src[advanced_src.index("} else if (type === 'pintle')"):]
    pintle = pintle[:pintle.index("} else if (type === 'swirl')")]
    assert 'id="outer_diameter"' in pintle, \
        'alan pintle dalında üretilmiyor (okuma pintle dalında)'


def test_b3_15_dis_cap_yuk_tasiyor(istemci):
    """Sabit sayı atıl değildi: 50 -> 70 mm gövde et kalınlığını değiştirir.

    V301/E1: eski üst değer 120 mm idi; bu gövdenin çözülen kamarası
    79,8 mm iç çaplıdır ve 120 mm'lik enjektör gövdesi kamaraya SIĞMAZ —
    uç artık bunu 422 ``pintle_wider_than_chamber`` ile reddediyor
    (geometrik kapı, kaynaksız eşik yok). Kalemin iddiası (dış çap yük
    taşır) kamaraya sığan iki değerle aynen ölçülür.

    v3.0.1 port kulvarı: grain dış çapı artık son port çapı olduğu için bu
    gövdenin kendiliğinden çözülen kamarası ~53 mm'ye indi ve 70 mm'lik gövde
    yine sığmadı. Kalemin iddiası kamara boyutuna bağlı değildir; kamara iç
    çapı açıkça 100 mm verilir (kullanıcı kamara çapı korunur, artık yakıt
    yayımlanır), iki gövde de sığar.
    """
    sonuc = {}
    for dc in (50.0, 70.0):
        d, y = _post(istemci, '/calculate', {
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'injector_type': 'pintle',
            'outer_diameter': dc, 'pintle_diameter': 25.0,
            'secondary_holes': 'radial', 'chamber_diameter_input': 100.0})
        assert d == 200
        sonuc[dc] = ((y or {}).get('injector') or {}).get('body_wall_thickness')
    assert sonuc[50.0] is not None and sonuc[70.0] is not None
    assert abs(sonuc[70.0] - sonuc[50.0]) > 1.0, \
        'dış çap artık yük taşımıyor — kalemin gerekçesi düştü'


# --------------------------------------------------------------------------
# P12bB4-01 — /formulas §6.4 L* boyutu
# --------------------------------------------------------------------------
def _formul_kutulari(src, sol_taraf):
    return re.findall(r'\$%s = ([^$]+)\$' % re.escape(sol_taraf), src)


def test_b4_01_lstar_bagintisi_boyutca_dogru(formulas_src, istemci):
    """Yayımlanan L* ifadesi ürünün l_star'ını VERMELİ (9 mertebe değil).

    ÖLÇÜLDÜ (once.json): sayfa `V_c A_t / (m c*)` yazıyordu = 1,866e-10;
    ürünün `l_star` alanı 1,000000 m. Oran 5,36e9.
    """
    kutular = _formul_kutulari(formulas_src, r'L^*')
    assert kutular, '§6.4 L* kutusu bulunamadı'
    ifade = kutular[0].strip()
    assert ifade == r'\frac{V_c}{A_t}', (
        'yayımlanan ifade ürünün bağıntısı değil: %r' % ifade)

    d, y = _post(istemci, '/calculate', {
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o'})
    m = (y or {}).get('motor') or {}
    sayfa = m['chamber_volume_m3'] / m['throat_area']
    assert m['l_star'] == pytest.approx(sayfa, rel=1e-12), (
        'yayımlanan bağıntı ürünün l_star değerini vermiyor: '
        '%r vs %r' % (m['l_star'], sayfa))
    # Eski (boyutça yanlış) ifade dokuz mertebe uzağa düşüyordu — ölçüldü.
    eski = (m['chamber_volume_m3'] * m['throat_area']
            / (m['mdot_total'] * m['c_star']))
    assert sayfa / eski > 1e8, 'ölçüm senaryosu değişti (kalem gerekçesi)' 


# --------------------------------------------------------------------------
# P12bB4-16 — /formulas §1.1 ikinci Isp kutusunda g0
# --------------------------------------------------------------------------
def test_b4_16_ikinci_isp_kutusunda_g0_var(formulas_src, istemci):
    """Sağ taraf SANİYE vermeli; g0 yoksa m/s verir (9,807 kat sapma)."""
    kutular = _formul_kutulari(formulas_src, r'I_{sp}')
    assert len(kutular) >= 2, 'ikinci Isp kutusu bulunamadı'
    ikinci = kutular[1]
    assert 'g_0' in ikinci, 'ikinci kutuda g_0 yok — sağ taraf m/s'

    d, y = _post(istemci, '/calculate', {
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o',
        # kitap p1a B16 (karar §28-18 (a)) — SINIF (ii): bu bekçinin amacı
        # termokimya DEĞİL (/formulas §1.1 ikinci Isp kutusunun boyutu (g0)).
        # Eşik DEĞİŞMEDİ; testin kendi motoru 'gas' fazıyla sabitlendi (298,15
        # K gaz referansı = kalem öncesi geometri, BİT-AYNI). Sıvı
        # varsayılandaki yeni geometri sonucu defter kalemi KITAP-P1A-D4 (p1a
        # rapor §12).
        'oxidizer_phase': 'gas'})
    m = (y or {}).get('motor') or {}
    # T-ÇAPA-C2 (27 Eki): kutu İDEAL Isp ifadesidir; V301/H-PANEL (74b55500a,
    # Berke kararı) N2O/HTPB'ye c* verimi 0,89 uyguladı ve ``c_star`` artık
    # TESLİM edilen c*'tır (ideal × η). İdeal ifade teorik c*'la kurulur
    # (``c_star_theoretical``, verim uygulanmışsa yayımlanır); ölçüldü:
    # teslim c*'la 179,47 s (bant dışı) = 0,89 × ideal.
    gam = m['gamma']
    cstar = m.get('c_star_theoretical', m['c_star'])
    pe_pc = 1.0 / 20.0
    ideal = (cstar / (9.80665 * math.sqrt(gam))
             * math.sqrt(2 * gam / (gam - 1))
             * (2 / (gam + 1)) ** ((gam + 1) / (2 * (gam - 1)))
             * math.sqrt(1 - pe_pc ** ((gam - 1) / gam)))
    # Tablonun KENDİ ilan ettiği tipik bant: 200-450 s.
    assert 200.0 <= ideal <= 450.0, (
        'g0 ile bölünmüş sağ taraf tablonun tipik bandı dışında: %r' % ideal)
    assert 0.5 < ideal / m['isp'] < 2.0, \
        'sağ taraf ürünün Isp mertebesinde değil: %r vs %r' % (ideal, m['isp'])


# --------------------------------------------------------------------------
# P12bS1-03 — calculate_trajectory hayalet onay kutusu
# --------------------------------------------------------------------------
def test_s1_03_calculate_trajectory_onay_kutusu_gercek(advanced_src):
    """Okunan id sayfada TANIMLI olmalı ve varsayılanı ucun varsayılanı."""
    assert len(re.findall(
        r"getElementById\('calculate_trajectory'\)", advanced_src)) >= 1
    m = re.search(r'<input[^>]*\bid="calculate_trajectory"[^>]*>',
                  advanced_src)
    assert m, 'sayfada `#calculate_trajectory` alanı yok (hayalet okuma)'
    etiket = m.group(0)
    assert 'type="checkbox"' in etiket
    assert 'checked' in etiket, (
        'varsayılan işaretsiz: ucun varsayılanı True olduğu için yörünge '
        'yine sessizce kapanır')


def test_s1_03_uc_yorungeyi_yalniz_secime_gore_kapatir(istemci):
    """Kanal canlı: false -> ADLI atlama beyanı, anahtar yok/true -> uçuş.

    ÖH D15 / harita H2 ile GÜNCELLENDİ. Eski satır ``trajectory is None``
    bekliyordu; o gösterim "hesaplanmadı" ile "hesaplandı, sonuç yok"u
    ayırt edemiyor ve bu dosyanın kovaladığı sessiz-kanal sınıfının ta
    kendisi. Uç artık atlamayı adıyla söylüyor
    (``{skipped: True, reason: 'calculate_trajectory_false', message}``).
    Kanalın canlılığı iddiası AYNEN duruyor, yalnız kapalı yönün beklenen
    gösterimi null'dan beyana çevrildi.
    """
    temel = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
             'chamber_pressure': 20.0, 'fuel_type': 'htpb',
             'oxidizer_type': 'n2o'}
    d, y = _post(istemci, '/calculate', dict(temel, calculate_trajectory=True))
    assert d == 200 and isinstance((y or {}).get('trajectory'), dict)
    assert not (y or {})['trajectory'].get('skipped')
    d, y = _post(istemci, '/calculate', dict(temel, calculate_trajectory=False))
    assert d == 200
    kapali = (y or {}).get('trajectory')
    assert isinstance(kapali, dict) and kapali.get('skipped') is True, kapali
    assert kapali.get('reason') == 'calculate_trajectory_false'
    # Atlanan adım UÇUŞ SAYISI YAYIMLAMAZ.
    assert 'performance' not in kapali and 'trajectory' not in kapali


# --------------------------------------------------------------------------
# P12bS1-04 — USSA-1976'nın sunucu kopyası
# --------------------------------------------------------------------------
def test_s1_04_sunucu_kopyasi_tek_kaynakla_ayni(istemci):
    """`/api/altitude-to-pressure` deponun ISA tablosuyla BİREBİR olmalı.

    ÖLÇÜLDÜ (once.json): 30 km −%3,469 · 40 km −%15,780 · 50 km −%36,411.
    """
    from hrma.constants import isa_pressure
    for h in (0, 10000, 20000, 30000, 40000, 50000, 70000):
        d, y = _post(istemci, '/api/altitude-to-pressure', {'altitude': h})
        assert d == 200
        assert y['pressure'] == pytest.approx(isa_pressure(h) / 1e5,
                                              rel=1e-12), \
            '%d m: uç %r ⟷ tablo %r' % (h, y['pressure'], isa_pressure(h) / 1e5)


def test_s1_04_uctaki_ikinci_kopya_soruldu():
    """Uç kendi ISA formülünü tutmamalı — tek kaynak `hrma.constants`."""
    src = APP_PY.read_text(encoding='utf-8')
    i = src.index('def altitude_to_pressure')
    govde = src[i:i + 2600]
    assert 'isa_pressure' in govde, 'uç tek kaynağı kullanmıyor'
    assert not re.search(r'^\s*P0\s*=\s*1\.01325', govde, re.M), \
        'uçta yerel ISA sabit kopyası var'
    assert not re.search(r'^\s*T11\s*=', govde, re.M), \
        'basitleştirilmiş tek-katmanlı stratosfer kopyası geri gelmiş'
    assert not re.search(r'^\s*L\s*=\s*0\.0065', govde, re.M), \
        'uçta yerel lapse-rate kopyası var'


@pytest.mark.parametrize('deger', [float('-inf'), float('inf'),
                                   float('nan')])
def test_s1_04_sonlu_olmayan_irtifada_sayi_uydurulmuyor(istemci, deger):
    """Sonlu olmayan irtifa bir ölçüm değildir: uç SAYI UYDURMAZ.

    ÇEVRİLDİ (ÖH D30 / fix-29b). Bu test 200 + ``pressure is None``
    bekliyordu ve o gün doğruydu: uç gövdeyi null basıp 200 dönüyordu.
    Sözleşme SIKILAŞTI — ÖH D23 a2 / P13B4-12 kapısı (``hrma/app.py``,
    ``input_guard.num``) alan düzeyindeki istemci hatasını artık alan ADIYLA
    422 ile reddediyor (ölçüldü: ``num`` sonlu olmayan değeri hiç geçirmiyor,
    dolayısıyla uçtaki ``math.isfinite`` dalı artık ULAŞILAMAZ).

    İDDİA GEVŞETİLMEDİ, GENİŞLETİLDİ: yanıtta hiçbir basınç ya da sıcaklık
    sayısı yayımlanmaz VE ret gerekçelidir (alan adı + sebep). 200'e geri
    dönülürse ya da 422 gövdesine bir sayı sızarsa bu test kırmızı olur.
    Üç sonlu olmayan değer de sınanır; eskiden yalnız ``-inf`` vardı.
    """
    d, y = _post(istemci, '/api/altitude-to-pressure', {'altitude': deger})
    assert d == 422, (
        f'sonlu olmayan irtifa ({deger!r}) 422 ile reddedilmiyor: {d}')
    # Ret ANONİM değil: hangi alan, hangi sebep.
    alanlar = {a.get('field') for a in (y.get('invalid_fields') or [])}
    assert 'altitude' in alanlar, (
        f'ret alan adını söylemiyor: {y.get("invalid_fields")!r}')
    sebepler = {a.get('reason') for a in (y.get('invalid_fields') or [])}
    # ÖH D33-2 / app-api-uc a1 (OH-D32-15): gerekçe kodu KANONA çevrildi.
    # ``not_a_finite_number`` tek başına ÜÇ ayrı nedeni (``bool``,
    # çevrilemez metin, ``NaN``/``inf``) yutuyordu ve kardeş uç
    # ``/api/oxidizer-properties`` ayrımı zaten yapıyordu; ad bu dalgada
    # emekli oldu (ölçüm: ``D33-2/app-api-uc/a1/once_gerekce_kanonu.json``
    # K3). İDDİA DEĞİŞMEDİ — ret hâlâ gerekçeli, yalnız gerekçe artık
    # NEDENİ söylüyor: ``NaN``/``inf`` için ``not_finite``.
    assert 'not_finite' in sebepler, (
        f'ret sebebi yazılmamış: {sebepler!r}')
    assert 'not_a_finite_number' not in sebepler, (
        f'emekli gerekçe kodu geri gelmiş: {sebepler!r}')
    # Ve hiçbir sayı UYDURULMAMIŞ: gövdede basınç/sıcaklık yaprağı yok.
    for yaprak in ('pressure', 'temperature'):
        assert y.get(yaprak) is None, (
            f'422 gövdesinde {yaprak} sayısı sızmış: {y.get(yaprak)!r}')


# --------------------------------------------------------------------------
# P12bB1-10 — ipucu bandı ⟷ uç kapısı
# --------------------------------------------------------------------------
def _input_ozniteligi(src, fid):
    m = re.search(r'<input\b[^>]*\bid="%s"[^>]*>' % re.escape(fid), src)
    assert m, '%s alanı bulunamadı' % fid
    tag = m.group(0)
    al = lambda ad: (re.search(r'\b%s="([^"]*)"' % ad, tag) or [None, None])[1]
    return al('min'), al('max')


def test_b1_10_ipucu_bandi_uc_bandiyla_ayni(liquid_src):
    """Sayfanın reklam ettiği alt uç, uçta KABUL EDİLEN alt uç olmalı.

    Bant TEK KAYNAK: `hrma.validation.motor_validation.FORM_LIMITS['liquid']`.
    İki taraf ayrışırsa bu test kırmızı verir.
    """
    from hrma.validation.motor_validation import FORM_LIMITS
    bant = FORM_LIMITS['liquid']
    t_alt, t_ust, _ = bant['thrust']
    p_alt, p_ust, _ = bant['chamber_pressure']

    ip_t = re.search(r'Target thrust level for the liquid engine\.([^<]*)',
                     liquid_src)
    assert ip_t, 'itki ipucu bulunamadı'
    assert 'Small thrusters: %d-' % t_alt in ip_t.group(1), \
        'ipucu bandın altındaki bir alt ucu reklam ediyor: %s' % ip_t.group(1)

    ip_p = re.search(r'Combustion chamber operating pressure\.([^<]*)',
                     liquid_src)
    assert ip_p, 'basınç ipucu bulunamadı'
    assert 'Pressure-fed: %d-' % p_alt in ip_p.group(1), \
        'ipucu bandın altındaki bir alt ucu reklam ediyor: %s' % ip_p.group(1)

    assert _input_ozniteligi(liquid_src, 'thrust') == (
        str(int(t_alt)), str(int(t_ust))), 'itki alanının min/max bandı tutmuyor'
    assert _input_ozniteligi(liquid_src, 'chamber_pressure') == (
        str(int(p_alt)), str(int(p_ust))), 'Pc alanının min/max bandı tutmuyor'


def test_b1_10_ipucunun_alt_uclari_ucta_kabul_ediliyor(istemci):
    """Sayfanın önerdiği en küçük sayı gerçekten hesaplanabilmeli."""
    from hrma.validation.motor_validation import FORM_LIMITS
    bant = FORM_LIMITS['liquid']
    temel = {'motor_name': 'B110', 'thrust': 10000.0, 'burn_time': 30.0,
             'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
             'fuel_type': 'rp1', 'oxidizer_type': 'lox',
             'expansion_ratio': 12.0}
    d, _ = _post(istemci, '/calculate_liquid',
                 dict(temel, thrust=float(bant['thrust'][0])))
    assert d == 200, 'ipucunun itki alt ucu uçta reddediliyor'
    d, _ = _post(istemci, '/calculate_liquid',
                 dict(temel, chamber_pressure=float(
                     bant['chamber_pressure'][0])))
    assert d == 200, 'ipucunun Pc alt ucu uçta reddediliyor'


# --------------------------------------------------------------------------
# P12bS1-02 — hayalet alan envanteri (kısmen; ÖK-21 kalanı kilitli)
# --------------------------------------------------------------------------
SAYFALAR = ('index', 'liquid', 'solid', 'advanced', 'launch_site',
            'formulas')
# 'simple', 'uzaytek' girdileri (SAYFALAR + HAYALET_TABAN, ikisi de 0) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
#: ÖLÇÜLEN taban (sonra.json). Savcının "31" sayısı ÜST SINIRDIR: çalışma
#: anında `el.id = 'ad'` ile üretilen 13 id hayalet DEĞİLDİR. Gerçek sayı
#: onarım öncesi 18'di; P12bS1-03 iki tanesini kapattı -> 16.
#: ÖH D24 / defter P9B5-31 — `advanced` tabanı 6 -> 2, toplam 16 -> 12.
#: SIKILAŞTIRMADIR, gevşetme DEĞİLDİR. `advanced.html`deki koşulsuz `return;`
#: ve altındaki 58 satırlık ölü API akışı silindi (ölçüm:
#: docs/scofield/raw/OH/D24/ihracat/a2/once.json -> M5_P9B5_31). O ölü blok
#: dört hayalet id OKUYORDU — combustion_temp, molecular_weight, specific_heat,
#: thermal_conductivity — ve hiçbiri advanced.html'de TANIMLI değildi. Blok
#: gidince dördü de kapandı. Kayıt gerçeğe çekildi; bu sayı bir ÜST SINIRDIR ve
#: düşürülmesi kapıyı DARALTIR (ÖK-22'nin yasakladığı şey gevşetmedir).
#: Kalan iki id ÖK-21 kapsamındaydı (parametrik panel).
#: ÖH D37 A1a hibrit-beyan / OH-D33-06 — `advanced` tabanı 2 -> 0, toplam
#: 11 -> 9. SIKILAŞTIRMADIR: iki id'nin (enable_parametric, parametric_params)
#: tek okuyucusu `toggleParametricParams()` (çağıranı 0) söküldü; ana model
#: kararı (denetçi şartı 2: yama + taban BİRLİKTE).
HAYALET_TABAN = {
    'advanced': 0,
    # ÖH D30 · P12bB1-16: liquid.html'deki `motor_name` hayaleti SÖKÜLDÜ
    # (PDF künyesi artık tek çözücü `_liquidMotorName()` üzerinden geliyor),
    # envanter 9 -> 8 DÜŞTÜ. Mandal adıyla güncellenir; sayı YÜKSELTİLMEZ.
    'liquid': 8,       # 6 grafik kabı + sd_body_d + sd_prop_m
    'solid': 1,        # motor_name (ÖK-21: `|| SABİT` sökümü bu dalgada YASAK)
    'index': 0, 'launch_site': 0, 'formulas': 0,
}


def _tanimli_idler(src):
    ids = set(re.findall(
        r'<(?:input|select|textarea)\b[^>]*?\bid="([^"]+)"', src))
    ids |= set(re.findall(
        r"<(?:input|select|textarea)\b[^>]*?\bid='([^']+)'", src))
    ids |= set(re.findall(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*?\bid="([^"]+)"', src))
    ids |= set(re.findall(r'''\bid=\\?["']([A-Za-z0-9_\-]+)\\?["']''', src))
    ids |= set(re.findall(r'''\.id\s*=\s*["']([A-Za-z0-9_\-]+)["']''', src))
    return ids


def _okunan_idler(src):
    out = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", src))
    out |= set(re.findall(
        r"querySelector\(\s*['\"]#([A-Za-z0-9_\-]+)['\"]\s*\)", src))
    return out


def _hayaletler():
    paylasilan = ''
    for f in sorted(JSDIR.iterdir()):
        if f.suffix == '.js':
            paylasilan += f.read_text(encoding='utf-8', errors='ignore')
    paylasilan_ids = _tanimli_idler(paylasilan)
    out = {}
    for p in SAYFALAR:
        src = (SABLONLAR / (p + '.html')).read_text(encoding='utf-8')
        out[p] = sorted(_okunan_idler(src)
                        - (_tanimli_idler(src) | paylasilan_ids))
    return out


def test_s1_02_hayalet_alan_sayisi_artmiyor():
    """Yeni hayalet alan eklenemez; kapananlar geri gelemez.

    Bu kalemin kalanı ÖK-21 ile kilitli (`motor_name` üç sayfada `|| SABİT`
    yedeğine düşüyor; form katmanı sökümü D1'dedir ve EN SON yapılır). Bekçi
    ölçülen tabanı kilitler: sayı ARTAMAZ.
    """
    h = _hayaletler()
    artan = {p: sorted(h[p]) for p in SAYFALAR
             if len(h[p]) > HAYALET_TABAN[p]}
    assert not artan, 'yeni hayalet alan: %s' % artan
    assert 'calculate_trajectory' not in h['advanced'], \
        'P12bS1-03 geri gelmiş'


def test_s1_02_savcinin_31_sayisi_ust_sinir():
    """Ölçüm inceltmesi: çalışma anında üretilen id hayalet sayılmaz."""
    toplam = sum(len(v) for v in _hayaletler().values())
    assert toplam == sum(HAYALET_TABAN.values()), \
        'hayalet envanteri kaydından saptı: %d' % toplam
    assert toplam < 31, 'savcının üst sınırı aşıldı'


# --------------------------------------------------------------------------
# TABAN BEKÇİLERİ — ölçümle çürütülen (daha önce kapanmış) kalemler
# --------------------------------------------------------------------------
def test_b4_03_saha_rakimi_hem_gonderiliyor_hem_hukme_giriyor(istemci):
    """P12bB4-03 ÇÜRÜTÜLDÜ: yük rakımı taşıyor VE çözücü onu kullanıyor.

    Kalem "altı ad denendi, apoje bit-özdeş" diyordu. ÖLÇÜLDÜ (once.json,
    onarım ÖNCESİ taban): apoje 15.432,04 m (0 m) ⟷ 28.274,15 m (3.951,2 m).
    Bu bekçi o kapalı hâli kilitler.
    """
    src = LAUNCH_SITE.read_text(encoding='utf-8')
    gf = src[src.index("el('ls-fly').addEventListener"):]
    gf = gf[:20000]
    assert 'launch_altitude' in gf, 'uçuş yükü saha rakımını taşımıyor'

    apoje = {}
    for h in (0.0, 3951.2):
        d, y = _post(istemci, '/api/six-dof-analysis', {
            'body_diameter': 0.15, 'body_length': 3.0, 'nose_length': 0.5,
            'nose_type': 'ogive', 'dry_mass': 18.0, 'propellant_mass': 18.0,
            'thrust': 6500.0, 'burn_time': 7.5, 'cd0': 0.45, 'fin_count': 4,
            'fin_root_chord': 0.20, 'fin_tip_chord': 0.10, 'fin_span': 0.11,
            'fin_sweep': 0.08, 'launch_elevation_deg': 84,
            'launch_azimuth_deg': 90, 'rail_length': 5, 'wind_speed': 6,
            'wind_direction_deg': 270, 't_max': 400, 'latitude_deg': -16.5,
            'launch_altitude': h})
        assert d == 200
        s = (y or {}).get('summary') or y
        apoje[h] = s.get('apogee')
    assert apoje[0.0] and apoje[3951.2]
    assert abs(apoje[3951.2] - apoje[0.0]) > 100.0, \
        'rakım yine etkisiz: %r ⟷ %r' % (apoje[0.0], apoje[3951.2])


def test_b3_16_ihracat_kunyesi_cozucunun_parametrelerini_okur(advanced_src):
    """P12bB3-16 ÇÜRÜTÜLDÜ (a1'de onarıldı): künye artık sabite düşmüyor."""
    g = _blok(advanced_src, r'async function exportRegressionData\s*\(')
    assert re.search(r"\['Marxman a', p\.a", g), \
        'Marxman a çözücünün yayımladığı parametreden okunmuyor'
    assert re.search(r"\['Marxman n', p\.n", g), \
        'Marxman n çözücünün yayımladığı parametreden okunmuyor'
    assert "formVal('fuel_type')" in g, 'Fuel satırının form yedeği yok'
    assert "formVal('oxidizer_type')" in g, 'Oxidizer satırının form yedeği yok'
    assert not re.search(r"\['Marxman a', 3\.68e-0?5", g)
