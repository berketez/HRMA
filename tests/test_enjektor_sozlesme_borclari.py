# -*- coding: utf-8 -*-
"""Enjektör/kararlılık SÖZLEŞME BORÇLARI (v2.6.27, otuz ikinci parti).

Defterden üç kalem, üçü de "aynı sayı iki yerde / aynı ad iki anlam" sınıfı:

**Kalem 1 — chug eşiğinin 4. ve 5. kopyası.** ΔP/Pc eşik çifti (0,15 / 0,20)
parti 27'de TEK kaynağa (``hrma/analysis/acoustic_modes.py``) bağlanmıştı ama
iki kopya bilerek dar devirde bırakılmıştı: ``engines/injector_design.py``
kendi sabitlerini tanımlıyordu, ``utils/injector_design.py`` ise eşiği
kullanıcıya giden UYARI METNİNİN içine gömüyordu (">=15%"). Dize kopyası en
sinsisidir: sabit değişince kod yeni eşiğe göre boyutlandırır, ekrandaki
cümle ESKİ sayıyı savunmaya devam eder. Bu dosyanın bekçileri değer eşitliğine
DEĞİL, türetmeye bakar: eşik koşum sırasında değiştirilir ve metnin/kararın
onunla birlikte kıpırdadığı ÖLÇÜLÜR (literal geri gelirse kırmızı).

**Kalem 2 — hibrit τ_c çaprazı.** Sıvı motorda kamara zaman sabitinin İKİ
yolu (τ_c = L*/(c*Γ²) ve kalış süresi ρV/ṁ) karşılaştırılıp kalıntı
yayımlanıyordu; hibritte ikizi yoktu. Alan biçimi ORTAK yardımcıdan gelir
(``liquid_rocket_engine.tau_c_vs_residence_time_field``) — ikinci bir sözlük
tanımı yazılmaz. Kalıntının kaynağı hibritte ÖLÇÜLDÜ ve tektir: boğaz debi
katsayısı (oran = 1/C_D, fark 2,2e-16).

**Kalem 3 — ``injector_design.discharge_coefficient`` AD ÇAKIŞMASI.**
Kullanıcı 0,70 gönderirken yanıtta 0,78 yazıyordu. Ölçüm (parti öncesi):

    yanit.injector.discharge_coefficient        = 0.7   (utils bloğu)
    yanit.injector_design.discharge_coefficient = 0.78  (devre çözücüsü)

İki blok AYNI ADI taşıyor, iki farklı büyüklük yayımlıyordu; kullanıcının
değeri hibrit motora HİÇ ulaşmıyordu. Kök kapatıldı: değer devre
çözücüsünün KENDİ cebrine girdi olarak verilir (ṁ ∝ Cd hem SPI hem NHNE
dalında tam doğrusaldır), verilmezse alan tablodan gelir ve gerekçesi bunu
söyler.
"""

import ast
import copy
import os
import re
import sys
import warnings

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis import acoustic_modes                      # noqa: E402
from hrma.engines import injector_design as eid               # noqa: E402
from hrma.engines import liquid_rocket_engine as lre          # noqa: E402
from hrma.utils import injector_design as uid                 # noqa: E402
from hrma.engines.hybrid_rocket_engine import (               # noqa: E402
    THROAT_DISCHARGE_COEFFICIENT,
    HybridRocketEngine,
)
from tests.test_hybrid_input_wiring import BASE, HEADERS      # noqa: E402

ENGINES_INJ_PY = os.path.join(REPO_ROOT, 'hrma', 'engines', 'injector_design.py')
UTILS_INJ_PY = os.path.join(REPO_ROOT, 'hrma', 'utils', 'injector_design.py')
HYBRID_PY = os.path.join(REPO_ROOT, 'hrma', 'engines',
                         'hybrid_rocket_engine.py')
LIQUID_PY = os.path.join(REPO_ROOT, 'hrma', 'engines',
                         'liquid_rocket_engine.py')
APP_PY = os.path.join(REPO_ROOT, 'hrma', 'app.py')

#: Sıvı motorun τ_c çaprazının ORTAK gövdesi. Göç bekçisi bu gövdeye bakar.
#:
#: --- ÖH D22 / P6B4-02 · BEKÇİ ÇEVRİLDİ (kusuru koruyordu) ------------------
#: Eskiden burada metnin TAMAMI (ortak gövde + sıvıya özgü kalıntı gerekçesi)
#: donduruluyor ve ``test_sivi_yorumu_gocten_sonra_BIT_AYNI`` "bir karakter
#: bile kaymasın" diyordu. Kaymaması gereken şey GÖÇÜN davranış nötrlüğüydü;
#: ama donan metnin kuyruğu YANLIŞ bir fizik iddiası taşıyordu ("kalıntı
#: sıvı zincirinin kendi ṁ⟷c* tutarlılığından; debi itki/Isp zincirinden
#: gelir, boğulmuş-boğaz özdeşliğinden DEĞİL"). Ölçüldü
#: (raw/OH/D22/sivi/a1/once_p6b402.json): debi TAM OLARAK boğulmuş-boğaz
#: özdeşliğinden geliyor — ṁ/(Pc·A_t/c*) − 1 = −%2,000000000 (C_D=0,98) ve
#: −%5,000000000 (C_D=0,95). Bekçi böylece bir ATIF YALANINI donduruyordu:
#: gerekçeyi düzeltmenin tek yolu bekçiyi kırmaktı.
#: Bekçi ÇEVRİLDİ: artık göç nötrlüğünü ORTAK GÖVDE üzerinden kilitler
#: (asıl göç iddiası buydu) ve kalıntı gerekçesinin ölçülmüş ayrışmayı
#: taşıdığını AYRICA sınar. Gevşeme yok: eski tek eşitlik yerine üç şart var.
SIVI_ORTAK_GOVDE_DONDURULMUS = (
    'Two independent routes to the SAME physical time: '
    'tau_c = L*/(c* Gamma^2) and the chamber residence time '
    'rho_gas*V_c/mdot. They are algebraically identical when '
    'mdot = Pc*A_t/c* holds exactly. The residual measured '
    'here is ')

#: Çaprazın HER motorda taşıması gereken çekirdek alan kümesi. Motora özgü
#: ek alanlar (sıvıda ölçülmüş kalıntı ayrışması) bunun ÜSTÜNE gelir.
CAPRAZ_CEKIRDEK_ALANLAR = {'tau_c_s', 'residence_time_s', 'ratio',
                           'interpretation'}

#: Defterin tarif ettiği kabul bandı: kalış süresi / τ_c oranı buraya
#: düşmeli. Band KÖRELTİLMEZ — düşmüyorsa sebebi ölçülüp raporlanır.
ORAN_BANDI = (1.00, 1.10)


def oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _hibrit(**degisiklik):
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        return motor, motor.calculate()


@pytest.fixture(scope='module')
def hibrit_taban():
    return _hibrit()


@pytest.fixture(scope='module')
def hibrit_cd_070():
    return _hibrit(discharge_coefficient=0.70)


@pytest.fixture(scope='module')
def sivi_cevrim():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        eng = lre.LiquidRocketEngine(
            thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
            fuel_type='rp1', oxidizer_type='lox',
            cooling_type='regenerative', injector_type='impinging')
        sonuc = eng.calculate_performance()
    return sonuc['combustion_analysis']['stability_analysis']['chug_loop']


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _enj_spec(**ek):
    spec = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
            'mdot_ox': 0.4, 'rho_ox': 1220.0, 'Pc_bar': 20.0,
            'dp_ratio_ox': 0.20}
    spec.update(ek)
    return spec


# ===========================================================================
# KALEM 1 — eşik tek kaynak: kimlik + TÜRETME
# ===========================================================================
def test_esik_kimlik_zinciri():
    """Takma adlar AYNI NESNEYE bağlı olmalı — "aynı değer" YETMEZ.

    Değer eşitliği iki ayrı sabitin bugün aynı sayıyı taşımasıyla da
    sağlanır; kusur tam olarak buydu. Kimlik (``is``) ancak tek kaynaktan
    ithal edilmişse sağlanır.
    """
    kaynak_min = acoustic_modes.CHUG_DP_RATIO_MINIMUM
    kaynak_rec = acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    assert eid.CHUG_DP_PC_MIN is kaynak_min
    assert eid.CHUG_DP_PC_RECOMMENDED is kaynak_rec
    # utils modülü de aynı NESNEYİ okuyor (kendi kopyasını tutmuyor)
    assert uid.CHUG_DP_RATIO_MINIMUM is kaynak_min
    assert uid.CHUG_DP_RATIO_RECOMMENDED is kaynak_rec
    # Göç sessiz sayı değişikliği DEĞİLDİR
    assert kaynak_min == 0.15 and kaynak_rec == 0.20


def _sabit_atamalari(yol, hedefler):
    """AST: dosyadaki `AD = <sayı>` atamalarından hedef sayıya eşit olanlar."""
    agac = ast.parse(oku(yol), filename=yol)
    bulunan = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Assign):
            continue
        if not isinstance(dugum.value, ast.Constant):
            continue
        deger = dugum.value.value
        if not isinstance(deger, float):
            continue
        adlar = [h.id for h in dugum.targets if isinstance(h, ast.Name)]
        if any(abs(deger - h) < 1e-12 for h in hedefler):
            for ad in adlar:
                bulunan.append((ad, deger, dugum.lineno))
    return bulunan


def _sayi_gecisleri(yol, hedefler):
    """AST: hedef sayının dosyadaki HER geçişi — atama olmak ZORUNDA değil.

    ``_sabit_atamalari``nın genişletilmişi (savcı §3.1-7). Ölçülen kusur
    tam olarak atama OLMAYAN geçişlerdi: ``utils/injector_design.py:1065``
    sayıyı bir ``Compare`` operandı olarak taşıyor, ``engines/
    injector_design.py:1490-1491`` ise ``spec.get(..., 0.20)`` çağrı
    varsayılanı olarak. İkisi de ``ast.Assign`` taramasında görünmez.

    Dönüş: ``(sahip, değer, satır, düğüm_tipi)``. Sahip satır numarasından
    bağımsızdır ki defter kod kaydıkça çürümesin.
    """
    kaynak = oku(yol)
    agac = ast.parse(kaynak, filename=yol)
    satirlar = kaynak.split('\n')
    ebeveyn = {}
    for ust in ast.walk(agac):
        for cocuk in ast.iter_child_nodes(ust):
            ebeveyn[cocuk] = ust
    bulunan = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Constant):
            continue
        deger = dugum.value
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            continue
        if not any(abs(deger - h) < 1e-12 for h in hedefler):
            continue
        sahip, tip, n = None, None, dugum
        while n in ebeveyn:
            ust = ebeveyn[n]
            tip = type(ust).__name__
            if isinstance(ust, ast.Assign):
                for hedef in ust.targets:
                    if isinstance(hedef, ast.Name):
                        sahip = hedef.id
                    elif isinstance(hedef, ast.Attribute):
                        sahip = hedef.attr
                break
            if isinstance(ust, ast.Dict):
                for anahtar, d in zip(ust.keys, ust.values):
                    if d is n and isinstance(anahtar, ast.Constant):
                        sahip = str(anahtar.value)
                break
            if isinstance(ust, ast.Compare):
                sol = ust.left
                sahip = (sol.attr if isinstance(sol, ast.Attribute)
                         else sol.id if isinstance(sol, ast.Name) else None)
                break
            if isinstance(ust, ast.keyword):
                sahip = ust.arg
                break
            if isinstance(ust, ast.Call):
                for arg in ust.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        sahip = arg.value
                        break
                break
            n = ust
        bulunan.append((sahip, deger, dugum.lineno, tip,
                        satirlar[dugum.lineno - 1].strip()[:88]))
    return bulunan


#: Bu iki dosyada mekanik olarak 0,15/0,20 taşıyan AMA chug ΔP/Pc kuralı
#: OLMAYAN geçişler. Gerekçesiz muafiyet yoktur.
INJ_SEMANTIK_DISI = {
    ('hrma/utils/injector_design.py', 'INJECTOR_PLATE_MIN_LIGAMENT'):
        'plaka ligament kalınlığı alt sınırı [mm] — basınç oranı değil',
}


def test_iki_dosyada_esik_sabiti_yeniden_dogmadi():
    """Eşik çifti bu iki dosyada SAYI olarak bir daha tanımlanamaz.

    Tarama AST üstündedir: yorum/docstring tarihçeyi anlatabilir (anlatmak
    ZORUNDADIR), kod sayıyı ikinci kez yazamaz. Adı 'CHUG' geçen atamalar
    özellikle aranır — eski kusur tam olarak o adlarla doğmuştu.

    KAPSAM BEYANI: bu bekçi yalnız ADIYLA doğan kopyayı görür. Sayının
    adsız (``Compare`` operandı) ya da başka adla doğması aşağıdaki
    ``test_iki_dosyada_esik_DEGERI_ciplak_dogmadi`` ile ölçülür.
    """
    for yol in (ENGINES_INJ_PY, UTILS_INJ_PY):
        chug_sabitleri = [k for k in _sabit_atamalari(yol, (0.15, 0.20))
                          if 'CHUG' in k[0].upper()]
        assert not chug_sabitleri, (
            f'{os.path.relpath(yol, REPO_ROOT)}: chug eşiği SAYI olarak '
            f'yeniden tanımlanmış {chug_sabitleri}. Tek tanım yeri '
            'hrma/analysis/acoustic_modes.py — oradan ithal et.')


@pytest.mark.xfail(strict=True, reason=(
    'ÖH Z5S / P10-A (P10B1-10) — utils YARISI ÖDENDİ: '
    '`self.delta_P_inj < 0.2 * self.P_c` artık '
    'CHUG_DP_RATIO_RECOMMENDED\'dan türetiliyor ve utils tarafında tek '
    'ihlal kalmadı (ölçüldü: 2026-08-28). KALAN ihlaller ENGINES '
    'tarafındadır ve o dosya bu partinin mülkü DEĞİLDİR: '
    '`spec.get(\'dp_ratio_ox\', 0.20)` + `spec.get(\'dp_ratio_fuel\', 0.20)` '
    'gerçek kopyalar; MANIFOLD_V_RATIO_MAX / GAS_ANNULUS_GAP_MIN_MM / '
    'USER_CD_RANGE ise chug ölçütü OLMAYAN geçişler (semantik muafiyet '
    'kaydı gerekiyor). İkisi de engines sahibinin kalemidir; onlar '
    'ödendiğinde bu satır yeşile döner ve işaret silinir'))
def test_iki_dosyada_esik_DEGERI_ciplak_dogmadi():
    """Sayı bu iki dosyada ADSIZ olarak da doğamaz.

    Kusurun ölçülen biçimi buydu: tekilleştirme ADLARI kapattı, DEĞERİ
    kapatmadı. Bu bekçi tekilleştirmenin ikinci yarısını sayar.
    """
    ihlaller = []
    for yol in (ENGINES_INJ_PY, UTILS_INJ_PY):
        bagil = os.path.relpath(yol, REPO_ROOT).replace(os.sep, '/')
        for sahip, deger, satir, tip, metin in _sayi_gecisleri(yol, (0.15, 0.20)):
            if (bagil, sahip) in INJ_SEMANTIK_DISI:
                continue
            ihlaller.append(f'  {bagil}:{satir} [{tip}/{sahip}] = {deger}  {metin}')
    assert not ihlaller, (
        'chug eşiği bu dosyalarda SAYI olarak yaşıyor (adı olsun olmasın):\n'
        + '\n'.join(ihlaller)
        + '\nTek tanım yeri hrma/analysis/acoustic_modes.py — ithal et.')


def test_dp_secimi_esikten_TURETILIYOR(monkeypatch):
    """utils: otomatik ΔP seçimi eşiğin KENDİSİNDEN gelmeli.

    Kusuru yeniden üreten değişiklik: 0.15/0.20 literallerinin geri gelmesi.
    Bekçi eşiği koşum sırasında değiştirir; literal geri gelirse ΔP eski
    sayıda kalır ve bu satır kırmızıya döner.
    """
    monkeypatch.setattr(uid, 'CHUG_DP_RATIO_RECOMMENDED', 0.40)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        enj = uid.InjectorDesign(mdot_ox=0.4, chamber_pressure=20.0,
                                 tank_pressure=60.0, oxidizer_density=1220,
                                 oxidizer_type='generic')
    # Tank bol: seçim 'optimal' dalına düşer ve YENİ eşikle boyutlanır.
    assert enj.delta_P_inj == pytest.approx(0.40 * 20.0, rel=1e-12), (
        'otomatik ΔP eşikten türetilmiyor (literal geri gelmiş olabilir)')


def test_uyari_metnindeki_yuzde_esikten_TURETILIYOR(monkeypatch):
    """utils: ">=15%" dizesi sabitten üretilmeli, elle yazılmamalı."""
    monkeypatch.setattr(uid, 'CHUG_DP_RATIO_MINIMUM', 0.25)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        enj = uid.InjectorDesign(mdot_ox=0.4, chamber_pressure=30.0,
                                 tank_pressure=31.0, oxidizer_density=1220,
                                 oxidizer_type='generic')
    assert enj._feed_warning is not None, 'besleme uyarısı hiç kurulmadı'
    assert '>=25%' in enj._feed_warning, (
        'uyarı metni eşikten türetilmiyor — gömülü literal geri gelmiş: '
        + enj._feed_warning)
    assert '>=15%' not in enj._feed_warning


def _sessiz_enjektor(**ek):
    """Uyarı gürültüsü olmadan bir InjectorDesign kur (jenerik sıvı)."""
    varsayilan = dict(mdot_ox=0.4, chamber_pressure=20.0, tank_pressure=60.0,
                      oxidizer_density=1220, oxidizer_type='generic')
    varsayilan.update(ek)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return uid.InjectorDesign(**varsayilan)


def test_check_warnings_KARARI_ve_METNI_esikten_TURETILIYOR(monkeypatch):
    """ÖH Z5S / P10-A (P10B1-11): bekçi körlüğünün kapatılması.

    ÖLÇÜLEN KÖRLÜK: bu dosyadaki tek-kaynak bekçileri ya NESNE KİMLİĞİ
    (``is kaynak_min``) ya da ``__init__`` boyutlandırma yolunu sınıyordu.
    ``_check_warnings`` içindeki ikili — kararın çıplak ``0.2`` literali ve
    cümlenin elle yazılmış ``"<20%"`` dizesi — İKİSİNİN DE kapsamı
    dışındaydı ve 0 eşleşmeyle geçiyordu.

    Bu bekçi kusurun DURDUĞU yerde, kusurun İKİ BİÇİMİNİ birden ölçer:
    eşik koşum sırasında değiştirilir; hem KARAR (uyarı yanıyor mu) hem de
    METİN (yüzde) yeni eşiği izlemek zorundadır. Literal geri gelirse ikisi
    de eski sayıda kalır ve bu satır kırmızıya döner.
    """
    # Taban: ΔP = %20·Pc tam eşikte -> uyarı YOK (kesin karşılaştırma <).
    enj = _sessiz_enjektor(pressure_drop=0.20 * 20.0)
    dusuk = [u for u in enj._check_warnings(30.0, 50000.0)
             if u.startswith('Low pressure drop')]
    assert not dusuk, f'eşikte uyarı yanmamalıydı: {dusuk}'

    # Eşik 0,40'a çekilir: AYNI tasarım artık eşiğin altında kalır.
    monkeypatch.setattr(uid, 'CHUG_DP_RATIO_RECOMMENDED', 0.40)
    enj2 = _sessiz_enjektor(pressure_drop=0.20 * 20.0)
    dusuk2 = [u for u in enj2._check_warnings(30.0, 50000.0)
              if u.startswith('Low pressure drop')]
    assert dusuk2, (
        'KARAR eşikten türetilmiyor: eşik 0,40 iken %20 ΔP hâlâ '
        '"düşük değil" sayıldı (çıplak 0.2 literali geri gelmiş olabilir)')
    assert '<40%' in dusuk2[0], (
        'METİN eşikten türetilmiyor — gömülü yüzde geri gelmiş: ' + dusuk2[0])
    assert '<20%' not in dusuk2[0]


def test_uyari_metninde_gomulu_literal_kalmadi():
    """Kaynak taraması: dize içinde donmuş yüzde/oran kalmadı.

    DESEN GENİŞLETİLDİ (savcı §3.1-7). Eskiden yalnız ``>=\\s*15\\s*%``
    aranıyordu; ölçülen kusur ise ``<20%`` biçimindeydi ve süzgeçten
    geçiyordu. Yeni desen "rakam + yüzde" olan HER gömülü dizeyi arar.

    Yanlış alarm değil, ölçülü: f-string parçalarında sayı biçimlendirme
    ``{...:.0f}%`` olarak durduğundan sabitten TÜRETİLEN metinler bu desene
    takılmaz (``DP_SOURCE_AUTO``, ``>={CHUG_DP_RATIO_MINIMUM*100:.0f}%``
    ölçüldü: temiz). Yakalanan tek dize elle yazılmış olandır.

    ÖH Z5S / P10-A (P10B1-10): ``xfail(strict=True)`` işareti BURADAN
    KALDIRILDI — borç ödendi. Kaldırılmadan önce ölçüldü: işaretle koşum
    ``XPASS(strict)`` veriyordu, yani bekçi artık gerçekten yeşil.
    Yakaladığı tek dize ``"Low pressure drop (<20% of chamber pressure)"``
    idi; o cümle şimdi ``f"...(<{CHUG_DP_RATIO_RECOMMENDED*100:.0f}% ..."``
    biçiminde sabitin KENDİSİNDEN üretiliyor (metin bit-aynı).
    """
    kaynak = oku(UTILS_INJ_PY)
    # Yalnız DİZE düğümleri taranır (yorumlar tarihçeyi anlatmakta serbest).
    agac = ast.parse(kaynak, filename=UTILS_INJ_PY)
    suclu = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
            if re.search(r'\d+\s*%', dugum.value):
                suclu.append((dugum.lineno, dugum.value[:60]))
    assert not suclu, (
        'chug eşiği yine bir METNİN içine gömülmüş (sabit değişince metin '
        f'yalan söyler): {suclu}')


def test_chug_kurali_metni_esikten_TURETILIYOR(monkeypatch):
    """engines: yayımlanan 'chug_rule' dizesi sabitlerden kurulmalı."""
    d = eid.design_injector(_enj_spec())
    assert d['stability']['chug_rule'] == 'dP/Pc >= 0.15-0.20 (NASA SP-8089)'
    monkeypatch.setattr(eid, 'CHUG_DP_PC_MIN', 0.31)
    monkeypatch.setattr(eid, 'CHUG_DP_PC_RECOMMENDED', 0.42)
    d2 = eid.design_injector(_enj_spec())
    assert d2['stability']['chug_rule'] == 'dP/Pc >= 0.31-0.42 (NASA SP-8089)', (
        'chug_rule metni sabitlerden türetilmiyor: ' + d2['stability']['chug_rule'])


def test_dp_kaynak_etiketi_esikten_TURETILIYOR():
    """'auto (20% of Pc)' etiketi de sabitten üretilir — metni AYNI kalır."""
    assert uid.DP_SOURCE_AUTO == 'auto (20% of Pc)'
    kaynak = oku(UTILS_INJ_PY)
    assert "DP_SOURCE_AUTO = f'auto (" in kaynak, (
        'etiket yeniden literale dönmüş (sabit değişirse etiket yalan söyler)')


# ===========================================================================
# KALEM 2 — hibrit τ_c çaprazı
# ===========================================================================
def test_sivi_yorumu_gocten_sonra_BIT_AYNI(sivi_cevrim):
    """Göç nötrlüğü ORTAK GÖVDEDE kilitli; kalıntı gerekçesi ÖLÇÜLMÜŞ olmalı.

    ÖH D22 / P6B4-02 — bu bekçi çevrildi; gerekçesi
    ``SIVI_ORTAK_GOVDE_DONDURULMUS`` künyesinde. Özet: eski hâli metnin
    TAMAMINI donduruyordu ve o metnin kuyruğu ölçümle yanlışlanan bir fizik
    iddiası taşıyordu, yani bekçi kusuru koruyordu. Gevşetilmedi: tek
    eşitliğin yerine üç şart geldi.
    """
    capraz = sivi_cevrim['tau_c_vs_residence_time']
    # 1) Göç iddiasının asıl konusu: ortak gövde bir karakter kaymamalı.
    assert capraz['interpretation'].startswith(SIVI_ORTAK_GOVDE_DONDURULMUS)
    # 2) Çekirdek alanlar eksiksiz.
    assert CAPRAZ_CEKIRDEK_ALANLAR <= set(capraz)
    # 3) Kalıntı gerekçesi artık TAHMİN değil ÖLÇÜM: ayrışma yayımlanmalı ve
    #    iki adlı terimin çarpımı yayımlanan oranı yeniden üretmeli.
    ayrisma = capraz['residual_decomposition']
    assert ayrisma['discharge_coefficient_term'] == pytest.approx(
        1.0 / ayrisma['throat_discharge_coefficient'], rel=1e-12)
    assert (ayrisma['discharge_coefficient_term']
            * ayrisma['rt_identity_term']) == pytest.approx(
        capraz['ratio'], rel=1e-9), (
        'ayrışma yayımlanan oranı yeniden üretmiyor: kalıntının gerekçesi '
        'yine ölçülmemiş bir iddiaya dönmüş')
    assert abs(ayrisma['unexplained_pct']) < 1e-6, ayrisma
    # 4) Eski YANLIŞ gerekçe geri gelmemeli (atıf yalanı nöbeti).
    assert 'not\nfrom the choked-throat identity' not in \
        capraz['interpretation'].replace(' ', '\n'), (
        'debinin boğulmuş-boğaz özdeşliğinden GELMEDİĞİ iddiası geri döndü; '
        'ölçüm bunun tersini söylüyor (mdot = Pc*A_t*C_D/c*)')


def test_hibrit_caprazi_var_ve_sivinin_ALAN_IKIZI(hibrit_taban, sivi_cevrim):
    """Hibrit çapraz, sıvıdakiyle AYNI çekirdek alanları ve ortak metni taşır.

    ÖH D22 / P6B4-02: eşitlik ``set(hibrit) == set(sıvı)`` idi. Sıvı artık
    ölçülmüş kalıntı ayrışmasını da yayımladığı için tam eşitlik sıvının
    onarımını yasaklardı — bekçi, çekirdek sözleşmeyi (ortak alanlar + ortak
    gövde + ayrışan kalıntı gerekçesi) kilitlemeye çevrildi. Hibrit kendi
    ayrışmasını yayımlamıyor; bu bir EKSİKTİR ve hibrit kulvarının işidir,
    bu bekçi onu sıvıyı geri sararak "çözmez".
    """
    _, sonuc = hibrit_taban
    capraz = sonuc['combustion_stability']['chug_loop'].get(
        'tau_c_vs_residence_time')
    assert capraz is not None, 'hibrit chug_loop τ_c çaprazını yayımlamıyor'
    assert CAPRAZ_CEKIRDEK_ALANLAR <= set(capraz)
    assert CAPRAZ_CEKIRDEK_ALANLAR <= set(
        sivi_cevrim['tau_c_vs_residence_time'])
    # Ortak gövde AYNI nesneden gelir; ayrışan yalnız kalıntı gerekçesidir.
    assert capraz['interpretation'].startswith(
        lre.TAU_C_RESIDENCE_COMMON_BASIS)
    assert sivi_cevrim['tau_c_vs_residence_time'][
        'interpretation'].startswith(lre.TAU_C_RESIDENCE_COMMON_BASIS)
    assert capraz['interpretation'] != \
        sivi_cevrim['tau_c_vs_residence_time']['interpretation'], (
        'hibritin kalıntı gerekçesi sıvınınkinin kopyası olamaz: debi '
        'zinciri farklıdır ve metin bunu söylemek ZORUNDADIR')


def test_ortak_metin_hibride_KOPYALANMADI():
    """Yapısal tek kaynak: ortak gövde hibrit dosyasında hiç geçmiyor."""
    hibrit = oku(HYBRID_PY)
    assert 'Two independent routes' not in hibrit, (
        'ortak çapraz metni hibrit dosyasına KOPYALANMIŞ — iki kopya '
        'sessizce ayrışır; ortak yardımcıyı çağır')
    assert 'tau_c_vs_residence_time_field' in hibrit, (
        'hibrit ortak yardımcıyı çağırmıyor')
    sivi = oku(LIQUID_PY)
    assert sivi.count('Two independent routes') == 1, (
        'ortak gövde sıvı dosyasında birden çok yerde tanımlı')


def test_hibrit_orani_DEFTER_BANDINDA(hibrit_taban):
    """Oran [1,00-1,10] bandına düşmeli (defter tarifi)."""
    _, sonuc = hibrit_taban
    oran = sonuc['combustion_stability']['chug_loop'][
        'tau_c_vs_residence_time']['ratio']
    lo, hi = ORAN_BANDI
    assert lo <= oran <= hi, (
        f'τ_c ↔ kalış süresi oranı bant dışı: {oran!r}. Bandı GENİŞLETME — '
        'önce sebebi ölç (ṁ ↔ c* zinciri, C_D, V_actual) ve rapora yaz.')


def test_hibrit_orani_BOGAZ_KATSAYISININ_TERSI(hibrit_taban):
    """Kalıntının kaynağı ÖLÇÜLDÜ ve tektir: oran = 1/C_D.

    İdeal özdeşlik ṁ = Pc·A_t/c* varsayar; hibrit boğazı
    A_t = ṁ·c*/(Pc·C_D) ile kurar. Bu bekçi oranı o sabite ÇAPRAZ kilitler:
    zincirin herhangi bir ucu (ṁ, c*, γ, MW, T_c, V_actual) sürüklenirse
    oran 1/C_D'den kayar ve burası kırmızıya döner.
    """
    _, sonuc = hibrit_taban
    oran = sonuc['combustion_stability']['chug_loop'][
        'tau_c_vs_residence_time']['ratio']
    # ÇAPA YENİLENDİ (ÖH D18 fix-11, 3 Eyl 2026): beklenen oran artık iki
    # terimli — D18 fizik-a1 (B3-05/B3-02, 779a1c6) boğazı kayan-denge
    # sonik noktadan çözüyor; ṁ = Pc·A_t/c*_eq iken A_t tek-γ c*'la kurulur,
    # dolayısıyla oran = (c*_denge/c*_tek-γ)/C_D. Motor bu bölümü
    # nozzle_flow_quasi1d.mass_flow_c_star_model_ratio adıyla YAYIMLAR
    # (uydurma değil: tests/test_d15_hibrit_a3.py::TestB205 aynı tanımı
    # kilitler); oranın 1 olduğu tek-γ yolunda eski 1/C_D özdeşliği aynen
    # geri gelir. ÖLÇÜLDÜ (main 60cd341): oran 1,028592 = 1,004002² / 0,98 —
    # c* model oranı chug döngüsüne İKİ KEZ giriyor (τ_c tek-γ c*'dan, kalış
    # süresi kayan-denge yoğunluğu/ṁ zincirinden). Bu bir MODEL KARIŞIMI
    # kalıntısıdır, uydurma değil; buradaki bekçi ölçülen ilişkiyi ADIYLA
    # kilitler, τ_c'nin kayan-dengeye taşınması D19 fizik-b kalemidir
    # (OH-D19: chug_loop τ_c c* modeli). Kare kalkınca bu satır kırmızı olur
    # ve oran (c*_denge/c*_tek-γ)/C_D'ye ya da 1/C_D'ye iner — o gün
    # yeniden çapalanır, bant genişletilmez.
    c_star_orani = sonuc['nozzle_flow_quasi1d']['mass_flow_c_star_model_ratio']
    assert 0.95 < c_star_orani < 1.05, c_star_orani
    beklenen = c_star_orani ** 2 / THROAT_DISCHARGE_COEFFICIENT
    assert oran == pytest.approx(beklenen, rel=1e-9), (
        f'oran {oran!r}, beklenen (c*_denge/c*_tek-γ)²/C_D = {beklenen!r}')
    # Beyan da bunu ADIYLA söylüyor (sessiz totoloji yasak)
    metin = sonuc['combustion_stability']['chug_loop'][
        'tau_c_vs_residence_time']['interpretation']
    assert 'C_D' in metin and '1/C_D' in metin


def test_hibrit_kalis_suresi_YAYIMLANAN_ALANLARDAN_dogrulaniyor(hibrit_taban):
    """τ = ρ_gaz·V_c/ṁ, motorun kendi yayımladığı alanlardan yeniden kurulur.

    Motorun iç değişkenine bakılmaz: bekçi yanıtın KENDİ alanlarını okur,
    yani yayımlanan sayı ile yayımlanan girdiler tutarlı olmak zorundadır.
    """
    _, sonuc = hibrit_taban
    rho = (float(sonuc['chamber_pressure']) * 1e5
           / ((8314.462618 / float(sonuc['molecular_weight']))
              * float(sonuc['chamber_temperature'])))
    beklenen = (float(sonuc['chamber_volume_actual_m3']) * rho
                / float(sonuc['mdot_total']))
    capraz = sonuc['combustion_stability']['chug_loop'][
        'tau_c_vs_residence_time']
    assert capraz['residence_time_s'] == pytest.approx(beklenen, rel=1e-12)
    assert capraz['ratio'] == pytest.approx(
        capraz['residence_time_s'] / capraz['tau_c_s'], rel=1e-12)


def test_girdi_eksikse_capraz_HIC_KONMAZ():
    """Uydurma sayı yasağı: hacim/debi çözülmediyse alan yayımlanmaz."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                   chamber_pressure=20.0,
                                   track_performance=False)
    assert motor._chamber_residence_time({}) is None
    assert motor._chamber_residence_time(
        {'chamber_pressure': 20.0, 'chamber_temperature': 1900.0,
         'molecular_weight': 21.0, 'mdot_total': 0.5}) is None, (
        'hacim yokken kalış süresi UYDURULUYOR')
    assert motor._chamber_gas_density(
        {'chamber_pressure': 20.0, 'chamber_temperature': 0.0,
         'molecular_weight': 21.0}) is None


# ===========================================================================
# KALEM 3 — discharge_coefficient AD ÇAKIŞMASI
# ===========================================================================
def test_kullanici_cd_yanita_TASINIYOR(hibrit_cd_070):
    """Kullanıcı 0,70 verdi → yanıt 0,70 yazar (defterin ölçümü kapandı)."""
    _, sonuc = hibrit_cd_070
    inj = sonuc['injector_design']
    assert inj['discharge_coefficient'] == pytest.approx(0.70, rel=1e-12), (
        f"kullanıcı Cd taşınmıyor: {inj['discharge_coefficient']!r}")
    assert inj['discharge_coefficient_basis'] == eid.USER_CD_BASIS
    beyan = inj['discharge_coefficient_input']
    assert beyan == {'value': 0.70, 'applied': True,
                     'basis': eid.USER_CD_BASIS}


def test_cd_verilmezse_TABLODAN_ve_gerekceli(hibrit_taban):
    """Kullanıcı vermezse alan tablodan gelir ve gerekçesi bunu söyler."""
    _, sonuc = hibrit_taban
    inj = sonuc['injector_design']
    assert inj['discharge_coefficient_input'] is None, (
        'kullanıcı Cd vermediği hâlde "kullanıcı girdisi" beyanı üretilmiş')
    assert 'L/D' in inj['discharge_coefficient_basis']
    assert inj['discharge_coefficient'] != 0.70


def test_kullanici_cd_GEOMETRIYI_degistiriyor(hibrit_taban, hibrit_cd_070):
    """Etiket değil ÇÖZÜM değişmeli: A ∝ 1/Cd (SPI/NHNE cebri).

    Kusuru yeniden üreten değişiklik "sayıyı yaz, çözümü bırak" olurdu;
    bu bekçi alanı ölçtüğü için o hamleyi yakalar.
    """
    _, taban = hibrit_taban
    _, kullanici = hibrit_cd_070
    a0 = taban['injector_design']['total_injector_area_mm2']
    a1 = kullanici['injector_design']['total_injector_area_mm2']
    cd0 = taban['injector_design']['discharge_coefficient']
    assert a1 / a0 == pytest.approx(cd0 / 0.70, rel=1e-9), (
        'alan kullanıcı Cd\'siyle yeniden çözülmemiş (yalnız etiket '
        f'değişmiş olabilir): A oranı {a1 / a0!r}, beklenen {cd0 / 0.70!r}')
    assert kullanici['injector_design']['orifice_diameter_mm'] > \
        taban['injector_design']['orifice_diameter_mm']


def test_bant_disi_cd_BEYANLA_dusuyor():
    """Bant dışı Cd sessizce kırpılmaz: _defaults_used kaydıyla düşer."""
    motor, sonuc = _hibrit(discharge_coefficient=1.5)
    assert motor.injector_cd_input is None
    assert any(k.startswith('discharge_coefficient(out_of_range')
               for k in motor._defaults_used), motor._defaults_used
    assert sonuc['injector_design']['discharge_coefficient_input'] is None
    motor2, _ = _hibrit(discharge_coefficient='abc')
    assert motor2.injector_cd_input is None
    assert any(k.startswith('discharge_coefficient(invalid')
               for k in motor2._defaults_used), motor2._defaults_used


def test_cd_bandi_TEK_KAYNAK():
    """Sıvı ve hibrit AYNI bandı okur; sayı iki dosyada yazılamaz."""
    assert eid.USER_CD_RANGE == (0.20, 1.0)
    sivi = oku(LIQUID_PY)
    assert "'discharge_coefficient', 0.20, 1.0" not in sivi, (
        'sıvı motor Cd bandını yeniden literal olarak yazmış')
    assert 'USER_CD_RANGE[0], USER_CD_RANGE[1]' in sivi
    assert 'USER_CD_RANGE' in oku(HYBRID_PY)
    # Modül ucu da bandı savunur (uç ValueError'ı bandın kendisinden kurar)
    for bozuk in (0.1, 1.5):
        with pytest.raises(ValueError):
            eid.design_injector(_enj_spec(cd=bozuk))


def test_swirl_dalinda_kullanici_cd_UYGULANMAZ_ama_beyan_edilir():
    """Basınç-swirl Cd'si geometriden gelir; kullanıcı değeri yutulmaz."""
    d = eid.design_injector(_enj_spec(injector_type='swirl', cd=0.70))
    assert d['ox_circuit']['cd'] != pytest.approx(0.70)
    assert d['user_cd']['applied'] is False
    assert d['user_cd']['value'] == 0.70
    assert 'comparison only' in d['user_cd']['basis']


def test_kullanici_cd_ile_LD_geometriden_cozuluyor():
    """Cd sabitken bile plaka kalınlığı verilmişse L/D geometriktir.

    Flip (Nurick) ölçütü L/D okur: kullanıcı Cd'si yüzünden yineleme
    atlanınca L/D'yi varsayılan 4,0'da bırakmak, hükmü kullanıcının
    plakasıyla ilgisi olmayan bir orana dayandırırdı.
    """
    d = eid.design_injector(_enj_spec(cd=0.70, orifice_length_m=0.003))
    oxc = d['ox_circuit']
    assert oxc['cd'] == pytest.approx(0.70)
    assert oxc['l_over_d'] == pytest.approx(
        3.0 / oxc['orifice_d_mm'], rel=1e-9)
    assert 'solved orifice diameter' in oxc['l_over_d_basis']


def test_cd_verilmeyince_beyan_alani_bos_kalir():
    """Beyan uydurulmaz: Cd gelmediyse user_cd None'dur."""
    assert eid.design_injector(_enj_spec())['user_cd'] is None


def test_kullanici_cd_IKI_DEVREYE_birden_uygulaniyor():
    """Çift devrede yarısı kullanıcıdan yarısı tablodan bir enjektör olamaz.

    (Sıvı motorun bugünkü yolu ``_apply_user_discharge_coefficient``
    üstünden gidiyor; bu bekçi modül SÖZLEŞMESİNİ kilitler ki iki yol
    ileride ayrışmasın.)
    """
    spec = {'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
            'mdot_ox': 2.0, 'mdot_fuel': 0.8, 'rho_ox': 1140.0,
            'rho_fuel': 810.0, 'Pc_bar': 50.0, 'dp_ratio_ox': 0.20,
            'dp_ratio_fuel': 0.20}
    taban = eid.design_injector(dict(spec))
    kullanici = eid.design_injector(dict(spec, cd=0.70))
    for devre in ('ox_circuit', 'fuel_circuit'):
        assert kullanici[devre]['cd'] == pytest.approx(0.70)
        assert (kullanici[devre]['total_area_mm2']
                / taban[devre]['total_area_mm2']) == pytest.approx(
                    taban[devre]['cd'] / 0.70, rel=1e-9), devre


# ---------------------------------------------------------------------------
# Uçtan uca — app.py kablosu çekilince kendiliğinden devreye girer
# ---------------------------------------------------------------------------
def _hibrit_kurucu_anahtarlari():
    """``/calculate``in ``HybridRocketEngine(...)`` çağrısının ANAHTAR adları.

    ÖLÇÜLEN KUSUR (P14M4-05b, savcı §3.1-8): bu yüklem eskiden ürün KAYNAK
    METNİNDE alt dizge arıyordu (``'discharge_coefficient' in govde``).
    Alt dizge, anahtarı **yorum satırında** da bulur; dolayısıyla kablo ile
    onu anlatan yorum BİRLİKTE sökülünce yüklem sessizce yön değiştiriyor,
    aşağıdaki çift de kendini silahsızlandırıyordu (mutasyon ölçümü: 9.250
    testte tek kırmızı yok, sayaç 1-skipped'te sabit).

    Yeni yüklem yapıya bakar: ``ast.Call`` -> ``keyword.arg``. Yorum artık
    yüklemi besleyemez. Desen aynı dosyadaki ``_sabit_atamalari``dan
    alınmıştır (bu depoda AST yeteneği zaten vardı).
    """
    src = oku(APP_PY)
    agac = ast.parse(src, filename=APP_PY)
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


def _rota_dekoratoru(dugum, yol):
    """``@app.route('<yol>', methods=[...])`` mi?"""
    return (isinstance(dugum, ast.Call)
            and isinstance(dugum.func, ast.Attribute)
            and dugum.func.attr == 'route'
            and dugum.args
            and isinstance(dugum.args[0], ast.Constant)
            and dugum.args[0].value == yol)


#: KABLONUN BUGÜNKÜ DURUMU — ölçüldü (app.py, /calculate hibrit kurucusu:
#: ``discharge_coefficient=data.get('discharge_coefficient')`` VAR).
#:
#: Bu sabit, aşağıdaki skip-armed çiftin kendini silahsızlandırmasını
#: engeller: çift, kablonun hangi yönde olduğuna göre birbirinin yerine
#: geçtiği için kablo SÖKÜLDÜĞÜNDE hiçbiri kırmızı olmuyordu (yalnız hangi
#: testin skip edildiği değişiyordu — dışarıdan görünmez). Bu satır yönü
#: DONDURUR: kablo geri sökülürse aşağıdaki bekçi kırmızıya döner.
KABLO_TAKILI_BEKLENEN = True


def test_kablo_YONU_dondurulmus():
    """Kablonun varlığı bir ÖLÇÜMdür; sessizce yön değiştiremez.

    ÖLÇÜLEN KUSUR (P14M4-05b): aşağıdaki skip-armed çift, kablo söküldüğünde
    yalnız *hangisinin* skip edildiğini değiştiriyor, ikisi de yeşil kalıyordu
    — yani desen ürünün gerilemesini GÖREMİYORDU. Bu satır o boşluğu kapatır:
    kablo bugünkü ölçülmüş yönünden saparsa burası kırmızı olur ve sapmanın
    bilerek yapıldığının deftere yazılmasını zorlar.
    """
    takili = 'discharge_coefficient' in _hibrit_kurucu_anahtarlari()
    assert takili is KABLO_TAKILI_BEKLENEN, (
        f'/calculate hibrit kurucusundaki discharge_coefficient kablosu '
        f'{"SÖKÜLMÜŞ" if KABLO_TAKILI_BEKLENEN else "ÇEKİLMİŞ"}. '
        'Bu bir davranış değişikliğidir: kullanıcının Cd\'si motora '
        f'{"artık ulaşmıyor" if KABLO_TAKILI_BEKLENEN else "artık ulaşıyor"}. '
        'Bilerek yapıldıysa KABLO_TAKILI_BEKLENEN güncellenir ve gerekçesi '
        'yazılır.')


def test_ucta_ad_cakismasi_kapandi(istemci):
    """/calculate: kullanıcı 0,70 gönderirse İKİ blok da 0,70 demeli.

    DÜRÜST SKIP: kablo yoksa bu bekçi kendiliğinden devreye girmez. Skip
    koşulu app.py'nin YAPISINA bakar (``ast.Call`` -> ``keyword.arg``),
    kaynak metnine değil — bir yorum satırı yüklemi besleyemez
    (P14M4-05b). Yön ayrıca ``test_kablo_YONU_dondurulmus`` ile kilitli.
    """
    if 'discharge_coefficient' not in _hibrit_kurucu_anahtarlari():
        pytest.skip(
            'app.py /calculate hibrit kurucusu discharge_coefficient '
            'anahtarını henüz geçirmiyor. Kablo: HybridRocketEngine(..., '
            "discharge_coefficient=data.get('discharge_coefficient')) — "
            'advanced.html kapısıyla BİRLİKTE inmelidir, yoksa '
            'test_stability_hibrit_chug.py::test_motora_ulasan_her_'
            'anahtarin_form_ucunda_karsiligi_var kırmızıya döner.')
    yuk = dict(copy.deepcopy(BASE), include_plots=False,
               discharge_coefficient=0.70)
    yanit = istemci.post('/calculate', json=yuk, headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    govde = yanit.get_json()
    assert govde['injector_design']['discharge_coefficient'] == \
        pytest.approx(0.70, rel=1e-12)
    # AD ÇAKIŞMASININ kendisi: aynı adı taşıyan iki blok artık aynı sayıyı
    # söylüyor (kullanıcı değeri verildiğinde).
    assert govde['injector']['discharge_coefficient'] == \
        pytest.approx(0.70, rel=1e-12)


def test_ucta_cd_bugun_hala_ayrisiyor_OLCULUYOR(istemci):
    """Kablo çekilene kadar açığın KENDİSİ ölçülür (sessiz beklemek yok).

    Bu bekçi ters yönlüdür: bugünkü ayrışmayı belgeler ve kablo çekildiği
    an KIRMIZI olur — böylece yukarıdaki skip'in unutulması imkânsızdır.
    (Yüklem AST üstünden okunur; P14M4-05b.)
    """
    if 'discharge_coefficient' in _hibrit_kurucu_anahtarlari():
        pytest.skip('kablo çekilmiş: ayrışma testi yerini uçtan uca '
                    'bekçiye bıraktı (yukarıdaki test artık koşuyor)')
    yuk = dict(copy.deepcopy(BASE), include_plots=False,
               discharge_coefficient=0.70)
    yanit = istemci.post('/calculate', json=yuk, headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    govde = yanit.get_json()
    assert govde['injector']['discharge_coefficient'] == \
        pytest.approx(0.70, rel=1e-12), (
        'utils bloğu kullanıcı Cd\'sini de mi kaybetti? Defter ölçümü '
        'bunun CANLI olduğunu söylüyordu.')
    assert govde['injector_design']['discharge_coefficient'] != \
        pytest.approx(0.70, rel=1e-12), (
        'uçta ayrışma kapanmış görünüyor — kablo çekildiyse bu testin '
        'yerini test_ucta_ad_cakismasi_kapandi alır, skip koşulunu '
        'güncelleyin')
