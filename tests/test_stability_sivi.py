"""F2b-2 — sıvı motorun chug bağlaması + eşiğin TEK KAYNAK bekçisi.

İKİ İŞ
------
**1. Eşik tekleştirme.** ΔP/Pc chug tasarım kuralının sayı çifti (0,20/0,15)
depoda DÖRT yerde tanımlıydı ve İKİ ayrı künyeyle savunuluyordu (tasarım
belgesi §1.1-1'in ölçtüğü üçe, F2b-2 taraması bir dördüncüsünü ekledi):

    hrma/analysis/acoustic_modes.py       0.20/0.15   Sutton Böl. 8 + SP-194
    hrma/engines/liquid_rocket_engine.py  0.15/0.20   SP-8089
    hrma/engines/injector_design.py       0.15/0.20   SP-8089
    hrma/analysis/transient_ballistics.py 0.15        SP-8089

Aynı sayının iki künyesi olamaz: künye ya sayının dayanağıdır ya değildir.
Hüküm (kaynağa inilerek, ``CHUG_THRESHOLD_SOURCE`` içinde yazılı): mekanizma
SP-194 Böl. 5-6'dan, sayı bandı tasarım pratiğinden (Sutton Böl. 8) gelir;
SP-8089 bu depoda BELGE olarak doğrulanmıştır (docs/STANDART_ATIFLARI.md,
NTRS 19760023196) ama bandın o belgede SAYFA düzeyinde geçtiği
doğrulanmamıştır — defterin kendi kuralı gereği bandın dayanağı yapılamaz.
Sayı DEĞİŞMEDİ; tanım tekleşti.

**2. Chug bağlaması.** Sıvı motorun oran kuralı (ΔP/Pc ≥ 0,20) artık tek
başına değil: ``hrma.stability.chug``un GERÇEK çevrimi (nötr eğri + baskın
kök) motorun kendi ΔP, L*, c* ve atomizasyon süresiyle koşuyor. Bu iki ölçüt
AYNI SORUYU farklı bilgiyle yanıtlıyor ve bu depoda ÇELİŞTİKLERİ ölçüldü —
o yüzden çelişkinin kendisi bir çıktı alanıdır (``rule_vs_loop``), sessiz
değil.

KAPSAM ETİKETİ ZORUNLU: çevrimin hükmü ``verdict_scope`` olmadan
yayımlanamaz (F2a karar 1 + sıkılaştırma); çıplak "STABLE"i kullanıcı "her
mekanizmaya karşı stabil" okur.
"""

import ast
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis import acoustic_modes                    # noqa: E402
from hrma.analysis import transient_ballistics              # noqa: E402
from hrma.engines import liquid_rocket_engine as lre        # noqa: E402
from hrma.stability import chug as chug_mod                 # noqa: E402
from hrma.engines.liquid_rocket_engine import (             # noqa: E402
    LiquidRocketEngine,
)

TABAN = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
             fuel_type='rp1', oxidizer_type='lox',
             cooling_type='regenerative', injector_type='impinging')


@pytest.fixture(scope='module')
def taban():
    eng = LiquidRocketEngine(**TABAN)
    return eng, eng.calculate_performance()


@pytest.fixture(scope='module')
def kararlilik(taban):
    return taban[1]['combustion_analysis']['stability_analysis']


@pytest.fixture(scope='module')
def cevrim(kararlilik):
    return kararlilik['chug_loop']


# ===========================================================================
# 1) EŞİK TEK KAYNAK
# ===========================================================================
#: Tanımın TEK sahibi. Diğer her modül buradan ithal eder.
KAYNAK_MODUL = 'hrma/analysis/acoustic_modes.py'

#: Eşiği ADIYLA taşıyan ama F2b-2'de SAHİPLİĞİ bu partide olmayan dosyalar.
#: Bunlar hâlâ kendi sayısını tanımlıyor; kalemleri devredildi. Liste DAR
#: tutulur ve her satırı kod kanıtlıdır. Bir satır kapanırsa (dosya artık
#: ithal ediyorsa) aşağıdaki bekçi KIRMIZI olur ve satırın silinmesini
#: zorlar — muafiyet listesi kendiliğinden çürüyemez.
DEVREDILEN_KOPYALAR = {
    'hrma/engines/injector_design.py': {
        'adlar': ('CHUG_DP_PC_MIN', 'CHUG_DP_PC_RECOMMENDED'),
        'devir': ('F2c / enjektör kalemi — bu parti sıvı motor + geçici '
                  'balistik dosyalarına sahipti; injector_design.py eş '
                  'zamanlı başka bir kulvarın dosyasıdır (paralel yazma '
                  'kuralı), o yüzden dokunulmadı.'),
    },
}

#: Muafiyet listesi tavanı: ölçülen borç 1 dosyadır. Yükseltmek, borcu
#: gizlemektir (eşik testi deseni: yastıksız).
DEVIR_TAVANI = 1


def test_chug_esigi_tek_kaynak():
    """Eşik çifti YALNIZ merkezî modülde SAYISAL olarak tanımlı olsun.

    Tarama AST üstündendir: docstring/yorum tarihçeyi anlatabilir (anlatmak
    ZORUNDADIR), ama kodda sayı olarak ikinci kez doğamaz.
    """
    hedefler = (0.20, 0.15)
    ihlaller = []
    for kok, _dizinler, dosyalar in os.walk(os.path.join(REPO_ROOT, 'hrma')):
        if '__pycache__' in kok:
            continue
        for dosya in dosyalar:
            if not dosya.endswith('.py'):
                continue
            tam = os.path.join(kok, dosya)
            bagil = os.path.relpath(tam, REPO_ROOT)
            if bagil.replace(os.sep, '/') == KAYNAK_MODUL:
                continue
            with open(tam, encoding='utf-8') as f:
                agac = ast.parse(f.read(), filename=tam)
            for dugum in ast.walk(agac):
                if not isinstance(dugum, ast.Assign):
                    continue
                adlar = [h.id for h in dugum.targets
                         if isinstance(h, ast.Name)]
                if not any('CHUG' in ad and ('DP' in ad or 'RATIO' in ad)
                           for ad in adlar):
                    continue
                if not isinstance(dugum.value, ast.Constant):
                    continue          # takma ad (Name) -> tek kaynak korunur
                if any(abs(dugum.value.value - h) < 1e-12 for h in hedefler):
                    ihlaller.append(
                        (bagil.replace(os.sep, '/'), adlar[0],
                         dugum.value.value, dugum.lineno))

    bilinen = {(yol, ad) for yol, kayit in DEVREDILEN_KOPYALAR.items()
               for ad in kayit['adlar']}
    yeni = [i for i in ihlaller if (i[0], i[1]) not in bilinen]
    assert not yeni, (
        'Chug eşiği YENİDEN kopyalanmış (tek kaynak kuralı):\n'
        + '\n'.join(f'  {y}:{s} {a} = {d}' for y, a, d, s in yeni)
        + f'\nTek tanım yeri: {KAYNAK_MODUL}. Oradan ithal et.')

    kapananlar = bilinen - {(i[0], i[1]) for i in ihlaller}
    assert not kapananlar, (
        f'Devir listesi ÇÜRÜMÜŞ: {sorted(kapananlar)} artık kendi sayısını '
        'tanımlamıyor. DEVREDILEN_KOPYALAR listesinden sil (muafiyet, borç '
        'kapandıktan sonra da durmaz).')
    assert len(DEVREDILEN_KOPYALAR) <= DEVIR_TAVANI


def test_esik_kullanicilari_ayni_NESNEYI_okuyor():
    """Takma adlar aynı nesneye bağlı olmalı — "aynı değer" YETMEZ.

    Değer eşitliği, iki ayrı sabitin bugün aynı sayıyı taşımasıyla da
    sağlanır; kusur tam olarak buydu. Kimlik (``is``) ise ancak tek kaynaktan
    ithal edilmişse sağlanır.
    """
    kaynak_min = acoustic_modes.CHUG_DP_RATIO_MINIMUM
    kaynak_rec = acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    assert lre.CHUG_DP_PC_MIN_LIQUID is kaynak_min
    assert lre.CHUG_DP_PC_RECOMMENDED_LIQUID is kaynak_rec
    assert transient_ballistics.DP_RATIO_WARN is kaynak_min
    assert chug_mod.CHUG_DP_RATIO_MINIMUM is kaynak_min
    assert chug_mod.CHUG_DP_RATIO_RECOMMENDED is kaynak_rec
    # Sayılar DEĞİŞMEDİ (göç sessiz sayı değişikliği değildir).
    assert kaynak_min == 0.15 and kaynak_rec == 0.20


def test_kunye_hukmu_tek_metinde_ve_beyanli():
    """Künye çelişkisi metinde ADIYLA çözülmüş olmalı."""
    metin = acoustic_modes.CHUG_THRESHOLD_SOURCE
    assert 'Sutton' in metin and 'SP-194' in metin
    assert 'SP-8089' in metin, (
        'İkinci künye yok sayılamaz: aynı bandı savunan diğer atıf ADIYLA '
        'anılmalı ve neden dayanak YAPILMADIĞI yazılmalı.')
    assert 'NOT been verified' in metin
    # Künye, çıktının içinde kullanıcıya da ulaşmalı.
    assert acoustic_modes.AcousticModeAnalyzer()._chug_report(
        None, None, 0.2)['threshold_source'] is metin


def test_model_gecerlilik_tabani_chug_esigiyle_karistirilmadi():
    """0,05 bir chug eşiği DEĞİL, çözücü durdurma korumasıdır.

    Aynı aileye sokulup tek kaynağa taşınsaydı, bir gün "chug eşiği 0,05'e
    düştü" diye okunurdu. İki kavram ayrı kalır ve ayrı beyan edilir.
    """
    assert transient_ballistics.DP_RATIO_UNSTABLE == 0.05
    assert transient_ballistics.DP_RATIO_UNSTABLE is not \
        acoustic_modes.CHUG_DP_RATIO_MINIMUM
    yol = os.path.join(REPO_ROOT, 'hrma', 'analysis',
                       'transient_ballistics.py')
    with open(yol, encoding='utf-8') as f:
        govde = f.read()
    assert 'ÇÖZÜCÜ GEÇERLİLİK TABANI' in govde


def test_i18n_bagli_uyari_metni_korundu():
    """Uyarı METNİ i18n regex'ine bağlıdır; eşik göçü onu kırmamalı.

    ``static/js/i18n_charts.js`` bu cümleyi regex ile yakalayıp Türkçeye
    çeviriyor. Sabit tek kaynağa taşınırken metnin bit-aynı kalması
    ŞARTTI (i18n bu partinin dosyası değil).
    """
    yol = os.path.join(REPO_ROOT, 'hrma', 'analysis',
                       'transient_ballistics.py')
    with open(yol, encoding='utf-8') as f:
        govde = f.read()
    assert '— chugging risk (SP-8089)' in govde
    js = os.path.join(REPO_ROOT, 'hrma', 'static', 'js', 'i18n_charts.js')
    with open(js, encoding='utf-8') as f:
        js_govde = f.read()
    assert re.search(r'chugging risk \\\(SP-8089\\\)', js_govde), (
        'i18n deseni değişmiş: uyarı metni ile desen BİRLİKTE '
        'değiştirilmelidir.')


# ===========================================================================
# 2) CHUG BAĞLAMASI
# ===========================================================================
def test_cevrim_gercekten_kosuyor(cevrim):
    """Sıvı motor artık oran kuralı DEĞİL, çevrimi de yayımlıyor."""
    assert cevrim['status'] == 'modelled'
    assert cevrim['model'] == 'lumped_capacitance_resistance_delay'
    for anahtar in ('dp_ratio_j', 'tau_s', 'tau_c_s', 'tau_over_tau_c',
                    'neutral_delay_s', 'neutral_tau_over_tau_c',
                    'growth_rate_1_s', 'frequency_hz'):
        assert anahtar in cevrim, anahtar


def test_cevrim_girdileri_motorun_KENDI_cozumunden(taban, cevrim, kararlilik):
    """J, τ ve τ_c uydurma değil: üçü de bu koşunun yayımlanan sayıları."""
    eng, sonuc = taban
    comb = sonuc['combustion_analysis']['combustion_analysis']
    # J = yayımlanan ΔP/Pc
    assert cevrim['dp_ratio_j'] == kararlilik['injector_dp_over_pc']
    # τ = yayımlanan atomizasyon süresi (ms -> s)
    assert cevrim['tau_s'] == pytest.approx(comb['mixing_time'] / 1000.0,
                                            rel=1e-12)
    # τ_c = L*/(c*Γ²), L* ve c* motorun kendi değerleri
    tc = cevrim['chamber_time_constant']
    assert tc['l_star_m'] == pytest.approx(eng._l_star(), rel=1e-12)
    assert tc['c_star_m_s'] == pytest.approx(float(eng.c_star), rel=1e-12)
    assert cevrim['tau_c_s'] == tc['tau_c_s']


def test_tau_c_ikinci_yolla_capraz_ve_fark_BEYANLI(cevrim, taban):
    """τ_c ile kalış süresi aynı büyüklüktür; kalan fark yayımlanmalı.

    ρV/ṁ = L*/(c*Γ²) özdeşliği ancak ṁ = P_c·A_t/c* tam sağlanırsa geçerli.
    Sıvı zincirinde ṁ itki/Isp yolundan geliyor; ÖLÇÜLEN artık %2,5. Bunu
    gizlemek "aynı yanıtta iki tanım" kusurudur — çıktıda duruyor.
    """
    capraz = cevrim['tau_c_vs_residence_time']
    comb = taban[1]['combustion_analysis']['combustion_analysis']
    assert capraz['residence_time_s'] == pytest.approx(
        comb['residence_time'] / 1000.0, rel=1e-12)
    assert capraz['ratio'] == pytest.approx(
        capraz['residence_time_s'] / capraz['tau_c_s'], rel=1e-12)
    # 17 Ağu 2026 ölçümü: 1,0255. Bant, kusur büyürse haber versin diye dar.
    assert 1.0 <= capraz['ratio'] <= 1.10, capraz['ratio']
    assert 'mdot' in capraz['interpretation']


def test_hukum_KAPSAM_ETIKETSIZ_yayimlanamaz(cevrim):
    """F2a karar 1 sıkılaştırması: çıplak hüküm yasak."""
    assert cevrim['verdict'] in ('stable', 'unstable', 'marginal')
    kapsam = cevrim['verdict_scope']
    assert kapsam and 'chug' in kapsam
    assert 'modeled mechanism only' in kapsam
    assert cevrim['verdict_basis']
    # Motorun GENEL hükmü hâlâ verilmiyor.
    blok_verdict = cevrim['verdict']
    assert blok_verdict != 'unknown'


def test_genel_hukum_hala_verilmiyor(kararlilik):
    """Chug hükmü, motorun genel kararlılık hükmüne TERFİ etmemeli."""
    assert kararlilik['stability_rating'] == 'unknown'
    assert kararlilik['acoustic_analysis'] == 'not_modelled'
    assert 'scope-labelled' in kararlilik['stability_rating_basis']


def test_oran_kurali_ile_cevrimin_iliskisi_OLCULU(cevrim, kararlilik):
    """Çelişki sessiz kalamaz: ilişki adıyla yayımlanır.

    ÖLÇÜLEN (17 Ağu 2026, taban motor): oran kuralı 'chug_margin_ok'
    (J = 0,22 ≥ 0,20) derken çevrim 'unstable' diyor — çünkü kural τ'yu ve
    τ_c'yi HİÇ görmüyor. Bu depoda üç örnek motorun ÜÇÜNDE de çelişki çıktı.
    """
    iliski = cevrim['rule_vs_loop']
    assert iliski['ratio_rule_rating'] == kararlilik['chug_rating']
    assert iliski['loop_verdict'] == cevrim['verdict']
    assert iliski['agreement'] in ('agree', 'disagree')
    beklenen = ('agree'
                if (iliski['ratio_rule_rating'] in ('chug_margin_ok',
                                                    'chug_margin_marginal'))
                == (iliski['loop_verdict'] == 'stable') else 'disagree')
    assert iliski['agreement'] == beklenen
    assert 'blind to the sensitive time lag' in iliski['interpretation']
    # τ'nun yönü de beyanlı olmalı (muhafazakâr taraf hangisi).
    assert 'conservative' in cevrim['tau_source'].lower()


def test_klasik_kural_capraz_kontrolu_cikitida(cevrim):
    """Kuralın nötr eğri üstünde NEREYE düştüğü ölçülü olarak yayımlanır."""
    capraz = cevrim['classical_rule_cross_check']
    assert capraz['rule_min_ratio'] == acoustic_modes.CHUG_DP_RATIO_MINIMUM
    assert capraz['rule_recommended_ratio'] == \
        acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    # J = 0,20'de nötr τ/τ_c = 0,865152... (tasarım belgesi §3.2 çapası)
    assert capraz['model_neutral_tau_over_tau_c_at_rule_recommended'] == \
        pytest.approx(0.8651517, rel=1e-6)


# ===========================================================================
# 3) BESLEME HATTI KAPISI (karar 5) — forma alan EKLENMEDİ
# ===========================================================================
def test_hat_verilmeyince_ataletsiz_ve_BEYANLI(cevrim):
    """Varsayılan koşuda ataletsiz model + açık beyan (uydurma hat yok)."""
    assert cevrim['inertance_included'] is False
    assert cevrim['tau_f_s'] is None
    assert cevrim['feed_line'] is None
    assert 'no layout default is assumed' in cevrim['inertance_basis']
    assert 'inertance-free feed line' in cevrim['verdict_scope']


def test_yerlesim_varsayimi_motora_KOPYALANMADI():
    """2,5 m'lik hat varsayımı chug yoluna sızmamalı."""
    yol = os.path.join(REPO_ROOT, 'hrma', 'engines', 'liquid_rocket_engine.py')
    with open(yol, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=yol)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name in (
                '_feed_line_inertance_inputs', '_chug_loop_block'):
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Constant) and isinstance(
                        alt.value, float) and abs(alt.value - 2.5) < 1e-9:
                    pytest.fail(
                        f'{dugum.name}:{alt.lineno} yerleşim varsayımı '
                        f'(2,5 m) kopyalanmış — karar 5 ihlali.')


def test_hat_verilince_ataletli_forma_geciyor(cevrim):
    """Çözücü tarafı HAZIR: gerçek hat verilirse ikinci mertebe model koşar.

    Forma alan EKLENMEDİ (karar 5, UI eş zamanlı değil); kapı override
    yolundan ölçülür. Aynı motorda τ_f > 0 olunca model adı ve kapsam
    etiketi DEĞİŞMELİ — yoksa "ataletli koştu" iddiası ekrandan okunamaz.
    """
    eng = LiquidRocketEngine(overrides={'feed_line_length_m': 1.5,
                                        'feed_line_diameter_mm': 12.0},
                             **TABAN)
    blok = eng.calculate_performance()[
        'combustion_analysis']['stability_analysis']['chug_loop']
    assert blok['inertance_included'] is True
    assert blok['model'] == 'lumped_inertance_capacitance_resistance_delay'
    assert blok['tau_f_s'] > 0
    assert blok['feed_line']['line_length_m'] == 1.5
    assert blok['feed_line']['line_area_m2'] == pytest.approx(
        3.141592653589793 * 0.012 ** 2 / 4.0, rel=1e-12)
    assert 'inertance-free' not in blok['verdict_scope']
    # Ataletsiz koşunun τ_c'si değişmemeli: hat yalnız τ_f getirir.
    assert blok['tau_c_s'] == pytest.approx(cevrim['tau_c_s'], rel=1e-12)


def test_eksik_girdi_uydurma_uretmez():
    """τ çözülemezse hüküm YOK, gerekçe VAR (uydurma yasağı)."""
    eng = LiquidRocketEngine(**TABAN)
    blok = eng._chug_loop_block(dp_pc=0.2, mixing_time=None, l_star_m=1.2,
                                rule_rating='chug_margin_ok')
    assert blok['status'] == 'NOT_EVALUATED'
    assert any('tau' in m for m in blok['missing_inputs'])
    assert 'verdict' not in blok
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in blok.values())
