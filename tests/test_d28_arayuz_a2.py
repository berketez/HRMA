# -*- coding: utf-8 -*-
"""ÖH D28 · arayuz a2 bekçileri.

Kalemler: OH-D26-21, OH-D27-14, P12aB2-05, P12bB1-12, P12bB1-18,
P12bB1-19, P12bB2-04, P12bB2-11, P12bB2-12.

Her bekçi ters-mutasyonla kırmızıya çevrilebilir olmalıdır
(docs/scofield/raw/OH/D28/arayuz/a2/mutasyon.json).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


LIQUID = 'hrma/templates/liquid.html'
SOLID = 'hrma/templates/solid.html'
APPJS = 'hrma/static/js/app.js'
DECK = 'hrma/static/js/motor_viz_deck.js'
I18N_COMMON = 'hrma/static/js/i18n_common.js'
I18N_PAGES = 'hrma/static/js/i18n_pages.js'
I18N_FORMULAS = 'hrma/static/js/i18n_formulas.js'
I18N_SHELL = 'hrma/static/js/i18n_shell.js'
ENGINE_LIQ = 'hrma/engines/liquid_rocket_engine.py'


def tr_bloklari(metin):
    """Dosyadaki TR sözlük diliminin (EN'den sonrası) başlangıç konumu.

    Not: kimi dosyada iç içe 'tr:' anahtarı da vardır; SÖZLÜK bloğu
    en SON eşleşmedir (EN bloğu her zaman önce gelir).
    """
    m = list(re.finditer(r"^\s*(?:tr|'tr'|\"tr\")\s*:\s*\{", metin, re.M))
    assert m, 'TR sözlük bloğu bulunamadı'
    return m[-1].start()


# ===================================================================== #
# OH-D26-21 — taşınan hüküm SONUCU ekranda                              #
# ===================================================================== #
D2621_ALANLAR = ('verdict_outcome', 'verdict_risk_level',
                 'verdict_outcome_source', 'verdict_safety_factor')


@pytest.mark.parametrize('alan', D2621_ALANLAR)
def test_d2621_hukum_sonucu_alanlari_dbasis_uzerinden_okunuyor(alan):
    """`structural_design_basis`'e TAŞINAN dört alanın ekranda tüketicisi var.

    Ölçülen kusur (a2/once.json): dördünün de okuması 0'dı; ekran
    "VERDICT ISSUED" derken taşınan UNSAFE/HIGH sonucunu söylemiyordu.
    """
    src = oku(APPJS)
    i = src.index('function structuralVerdictBlock')
    j = src.index('\nfunction ', i + 10)
    govde = src[i:j]
    # Alan ya doğrudan (`dbasis.<alan>`) ya künye döngüsünde (adıyla) okunur.
    assert (re.search(r'\bdbasis\.' + alan + r'\b', govde)
            or f"'{alan}'" in govde), (
        f'app.py `_carry_structural_verdict_outcome` bu alanı taşıyor ama '
        f'structuralVerdictBlock hiç okumuyor: {alan}')


def test_d2621_hukum_sonucu_rozeti_gercekten_baglaniyor():
    """Alan yalnız okunmuyor, bir ROZETE bağlanıyor (kanal var kapı var)."""
    src = oku(APPJS)
    m = re.search(r'badges \+= badge\(T\(\s*\'panel\.structural\.'
                  r'badgeVerdictOutcome\'.*?dbasis\.verdict_outcome',
                  src, re.S)
    assert m, 'verdict_outcome bir rozete bağlanmıyor'


def test_d2621_rozet_anahtari_en_ve_tr_bloklarinda():
    src = oku(I18N_COMMON)
    kes = tr_bloklari(src)
    anahtar = "'panel.structural.badgeVerdictOutcome':"
    assert anahtar in src[:kes], 'EN bloğunda anahtar yok'
    assert anahtar in src[kes:], 'TR bloğunda anahtar yok'


# ===================================================================== #
# OH-D27-14 — iki red kutusu yarışı                                     #
# ===================================================================== #
def test_d2714_guverte_basarisiz_olursa_govdesini_geri_alir():
    """`MotorVizDeck.create` null dönerken konteyneri BULDUĞU GİBİ bırakır."""
    src = oku(DECK)
    assert 'var oncekiGovde = host.innerHTML;' in src, (
        'güverte yazmadan önce konteynerin gövdesini saklamıyor')
    assert re.search(r'if \(!viz\) \{ govdeyiGeriAl\(\); return null; \}', src), (
        'mount başarısız olduğunda güverte kendi gövdesini geri almıyor — '
        'çağıranın yedek yolu ile aynı konteynerde iki red raporu yarışır')


def test_d2714_kati_sayfasi_yedek_yoldan_once_konteyneri_temizler():
    src = oku(SOLID)
    m = re.search(r"cadView\.innerHTML = '';\s*\n\s*const motorVisualization"
                  r" = create3DMotorVisualization", src)
    assert m, ('katı sayfası Plotly yedek yoluna düşmeden önce konteyneri '
               'temizlemiyor (OH-D27-14 ikinci ayak)')


# ===================================================================== #
# P12bB2-04 / -11 — çözücünün beyanı ekrana iner                        #
# ===================================================================== #
SOLID_KATEGORILER = (
    'computed_by_solver', 'reported_not_double_counted', 'structural_output',
    'test_bench_only', 'geometry_not_modelled',
    'result_of_catalogue_thermochemistry', 'informational',
)


def test_p12bb204_kati_sayfasi_unwired_inputs_okuyor():
    src = oku(SOLID)
    assert 'results.unwired_inputs' in src, (
        '/calculate_solid 27 alanlık `unwired_inputs` yayımlıyor, '
        'solid.html hiç okumuyordu')
    assert 'applySolidDeclarationBadges(results);' in src, (
        'beyan rozetleri sonuç akışına bağlanmamış')


@pytest.mark.parametrize('kategori', SOLID_KATEGORILER)
def test_p12bb204_her_kategorinin_metni_var(kategori):
    src = oku(SOLID)
    assert re.search(r'\b' + kategori + r':\s*function', src), (
        f'çözücünün "{kategori}" kategorisi için ekran metni yok')


def test_p12bb204_taninmayan_kategori_sessizce_yutulmaz():
    src = oku(SOLID)
    assert "TF('solid.msg.unwired_other'" in src, (
        'yeni bir kategori geldiğinde makine adıyla basılmıyor (fail-closed)')


def test_p12bb211_kirpma_ve_varsayilan_beyani_basiliyor():
    src = oku(SOLID)
    assert 'gd.clipped_inputs' in src, (
        '`grain_design.clipped_inputs` ekranda hiç yok — hesap sessizce '
        'kırpıp sayı üretiyor')
    assert 'gd.assumed_defaults' in src, (
        '`grain_design.assumed_defaults` ekranda hiç yok')


def test_p12bb204_yeni_anahtarlar_en_ve_tr_bloklarinda():
    src = oku(I18N_PAGES)
    kes = tr_bloklari(src)
    for k in ('solid.msg.unwired_computed_by_solver',
              'solid.msg.unwired_test_bench_only',
              'solid.msg.unwired_other',
              'solid.msg.clipped_input',
              'solid.msg.assumed_default',
              'solid.msg.divergence_not_published'):
        assert f"'{k}':" in src[:kes], f'EN bloğunda yok: {k}'
        assert f"'{k}':" in src[kes:], f'TR bloğunda yok: {k}'


# --- Katı beyan katmanının CANLI koşumu (node kum havuzu) ------------- #
NODE = shutil.which('node')

SOLID_BLOK_BAS = '// >>> SOLID_UNWIRED_BADGES_START'
SOLID_BLOK_SON = '// <<< SOLID_UNWIRED_BADGES_END'


def _solid_beyan_blogu():
    src = oku(SOLID)
    i = src.index(SOLID_BLOK_BAS)
    j = src.index(SOLID_BLOK_SON)
    return src[i:j]


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_p12bb204_canli_rozet_kosumu():
    """Blok node'da koşar: beyan edilen alanın grubuna rozet İNİYOR mu?"""
    blok = _solid_beyan_blogu()
    surucu = """
var _sayac = 0;
function Grup() { this.cocuklar = []; }
Grup.prototype.appendChild = function (n) { this.cocuklar.push(n); };
Grup.prototype.querySelector = function () { return null; };
function Eleman(id) { this.id = id; this.grup = new Grup(); }
Eleman.prototype.closest = function () { return this.grup; };
var ELEMANLAR = {};
['case_mass', 'star_radius', 'sampling_freq'].forEach(function (id) {
    ELEMANLAR[id] = new Eleman(id);
});
var document = {
    getElementById: function (id) { return ELEMANLAR[id] || null; },
    querySelectorAll: function () { return []; },
    createElement: function () {
        _sayac++;
        return { style: {}, setAttribute: function (k, v) { this[k] = v; },
                 remove: function () {}, textContent: '' };
    }
};
function T(k, f) { return f; }
function TF(k, p, f) {
    return String(f).replace(/\\{(\\w+)\\}/g, function (w, n) {
        return Object.prototype.hasOwnProperty.call(p, n) ? p[n] : w; });
}
__BLOK__
var sonuc = {
    unwired_inputs: { structural_output: ['case_mass'],
                      test_bench_only: ['sampling_freq'],
                      yepyeni_kategori: ['sayfada_yok'] },
    grain_design: { clipped_inputs: ['star_radius'], assumed_defaults: [] }
};
var kayip = applySolidDeclarationBadges(sonuc);
var cikti = {
    case_mass_rozet: ELEMANLAR.case_mass.grup.cocuklar.map(function (n) {
        return n.textContent; }),
    sampling_freq_rozet: ELEMANLAR.sampling_freq.grup.cocuklar.map(function (n) {
        return n.textContent; }),
    star_radius_rozet: ELEMANLAR.star_radius.grup.cocuklar.map(function (n) {
        return n.textContent; }),
    sayfada_olmayan: kayip
};
console.log(JSON.stringify(cikti));
"""
    kaynak = surucu.replace('__BLOK__', blok)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as f:
        f.write(kaynak)
        yol = f.name
    try:
        cp = subprocess.run([NODE, yol], capture_output=True, text=True,
                            timeout=60)
        assert cp.returncode == 0, cp.stderr[-2000:]
        d = json.loads(cp.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(yol)

    assert len(d['case_mass_rozet']) == 1, 'yapısal çıktı alanına rozet inmedi'
    assert 'structural analysis' in d['case_mass_rozet'][0].lower()
    assert len(d['sampling_freq_rozet']) == 1
    assert 'test-bench' in d['sampling_freq_rozet'][0].lower()
    assert len(d['star_radius_rozet']) == 1, 'kırpma rozeti inmedi'
    assert 'clipped' in d['star_radius_rozet'][0].lower()
    # Sayfada karşılığı olmayan beyan sessizce yutulmaz.
    assert d['sayfada_olmayan'] == ['sayfada_yok']


# ===================================================================== #
# P12bB2-12 — "Divergence Loss Factor" artık girdi değil                #
# ===================================================================== #
def test_p12bb212_alan_duzenlenemez_ve_kaynagini_soyluyor():
    src = oku(SOLID)
    m = re.search(r'<input[^>]*id="divergence_loss"[^>]*>', src)
    assert m, 'divergence_loss alanı yok'
    girdi = m.group(0)
    assert 'readonly' in girdi, (
        'alan ölü bir GİRDİ olarak duruyor: 0,02 -> 0,15 yanıtı bit-özdeş '
        '(a2/once_kosum.json) ve `unwired_inputs` beyanında da geçmiyor')
    assert 'data-solver-output="efficiency_analysis.divergence_losses"' in girdi
    # ÖH D33-KOLAY · denetim ŞARTI (arayuz): alan bir ÇIKTI olduğuna göre
    # ŞABLON ÖN-DOLGUSU TAŞIYAMAZ. `value="0.02"` ilk hesaptan ÖNCE ekranda
    # kazanılmamış bir sayı gösteriyordu ve kullanıcı onu çözücünün hükmü
    # sanıyordu (ölçüm: a1/once.json · M4_sablon_on_dolgu_var=true).
    assert not re.search(r'\bvalue="[^"]*"', girdi), (
        'çıktı alanı yine şablon ön-dolgusu taşıyor: ilk hesaptan önce '
        'kazanılmamış bir sayı ekranda duruyor')


def test_p12bb212_turetilen_deger_ve_kunye_basiliyor():
    src = oku(SOLID)
    assert 'eff.divergence_losses' in src, 'çözücünün kaybı okunmuyor'
    assert 'eff.divergence_losses_basis' in src, 'künye okunmuyor'
    assert 'updateDivergenceLoss(results);' in src, 'sonuç akışına bağlı değil'


def test_p12bb212_yayim_yoksa_sayi_uydurulmuyor():
    """Çözücü kayıp yayımlamadıysa alan doldurulmaz, nedeni yazılır."""
    src = oku(SOLID)
    i = src.index('function updateDivergenceLoss')
    govde = src[i:i + 2600]
    assert "T('solid.msg.divergence_not_published'" in govde
    j = govde.index("solid.msg.divergence_not_published")
    # ÖH D33-KOLAY · denetim ŞARTI (arayuz) — BEKÇİ ÇEVRİLDİ.
    # ESKİ ölçüt: "yayım-yok dalında HİÇ `el.value =` yok". O ölçüt
    # kusuru KORUYORDU: dal alana dokunmayınca ÖNCEKİ koşumun sayısı
    # (ya da şablon ön-dolgusu 0,02) ekranda OLDUĞU GİBİ kalıyordu ve
    # kullanıcı onu bu koşumun hükmü sanıyordu. YENİ ölçüt: dal alanı
    # TEMİZLER (`el.value = ''`) ama SAYI YAZMAZ; sayısal atama
    # (`(kayipPct / 100).toFixed(4)`) erken dönüşten SONRA gelir.
    dal = govde[:govde.index('return;', j)]
    assert "el.value = ''" in dal, (
        'yayım yokken alan temizlenmiyor: önceki koşumun sayısı ekranda '
        'kalıyor ve bu koşumun hükmü sanılıyor')
    assert 'removeAttribute' in dal and 'title' in dal, (
        'yayım yokken eski dayanak künyesi (title) kaldırılmıyor')
    atamalar = re.findall(r'el\.value\s*=\s*([^;]*);', dal)
    assert atamalar and all(a.strip() == "''" for a in atamalar), (
        'yayım yokken alana boş dizeden başka bir şey yazılıyor '
        '(fail-closed ihlali): %r' % atamalar)
    assert govde.index('(kayipPct / 100).toFixed(4)') > j, (
        'çözücünün kaybı yayım-yok dalından ÖNCE yazılıyor')


# ===================================================================== #
# P12bB1-18 / -19 — tank kartı künyeleri                                #
# ===================================================================== #
TANK_KUNYE = ('safety_margin_basis', 'total_propellant_mass_basis',
              'total_propellant_mass_nominal', 'pressure_rating_source',
              'safety_factor_source', 'sizing_model', 'burn_time_source',
              'ullage_fraction_basis')


@pytest.mark.parametrize('alan', TANK_KUNYE)
def test_p12bb118_tank_sayilari_kunyeli(alan):
    """Uç bu dayanağı yayımlıyor; tank kartı onu BASMAK zorunda."""
    eng = oku(ENGINE_LIQ)
    assert f"'{alan}'" in eng, f'uç bu alanı yayımlamıyor: {alan}'
    src = oku(LIQUID)
    # Ad yorumda geçiyor olabilir: alan YANITTAN okunmalı.
    assert re.search(r'tankData\.[\w.]*\b' + alan + r'\b', src), (
        f'"{alan}" uçtan geliyor ama tank kartında yanıttan hiç okunmuyor — '
        f'sayı künyesiz kalıyor')


TANK_MALZEME = ('material_key', 'yield_strength_mpa', 'cryogenic_suitability')


@pytest.mark.parametrize('alan', TANK_MALZEME)
def test_p12bb119_tank_malzemesi_kunyeli(alan):
    src = oku(LIQUID)
    assert re.search(r'\bst\.' + alan + r'\b|tankData\.[\w.]*\b'
                     + alan + r'\b', src), (
        f'LH2 (20 K) tankı "Carbon steel (generic, A36-class)" olarak '
        f'künyesiz basılıyor: {alan} okunmuyor')


def test_p12bb119_kriyojenik_hukum_iki_tankta_da_basiliyor():
    src = oku(LIQUID)
    assert 'function tankMalzemeHucresi' in src
    for tank in ('oxidizer_tank', 'fuel_tank'):
        assert f'tankMalzemeHucresi(tankData.{tank}.structural)' in src, (
            f'{tank} malzeme hücresi künyeli değil')
    i = src.index('function tankKriyoSatiri')
    govde = src[i:i + 1200]
    assert 'cs.verdict' in govde and 'cs.basis' in govde, (
        'kriyojenik hüküm ve gerekçesi basılmıyor')


# ===================================================================== #
# P12bB1-12 — tarayıcı kapısı ucun kapısını temsil eder                 #
# ===================================================================== #
def _motor_bantlari():
    eng = oku(ENGINE_LIQ)
    return {m.group(1): (float(m.group(2)), float(m.group(3)))
            for m in re.finditer(
                r"_override_val\(\s*'([\w]+)'\s*,\s*([-\d.eE]+)\s*,"
                r"\s*([-\d.eE]+)", eng)}


def _sayisal_girdiler():
    src = oku(LIQUID)
    out = {}
    for g in re.findall(r'<input\b[^>]*type="number"[^>]*>', src):
        mi = re.search(r'id="([^"]+)"', g)
        if not mi:
            continue
        lo = re.search(r'\bmin="([-\d.eE]+)"', g)
        hi = re.search(r'\bmax="([-\d.eE]+)"', g)
        out[mi.group(1)] = (float(lo.group(1)) if lo else None,
                            float(hi.group(1)) if hi else None)
    return out


#: Motorun `_override_val` bandı OLMAYAN sayısal alanlar. Kapı burada
#: UYDURULMAZ (fail-closed): sayı ancak ucun kendi bandından gelir.
#: Küme ölçüsüdür — sayı yükseltmek YASAK, yeni alan eklenirse ya bandı
#: uçta tanımlanır ya bu listeye GEREKÇEYLE girer.
BANTSIZ_ALANLAR = {
    'mixture_ratio', 'stoichiometric_of', 'discharge_coefficient',
    'characteristic_length', 'gimbal_actuator_arm', 'gimbal_ring_offset',
    'gimbal_bolt_circle', 'gimbal_bolt_count', 'traj_initial_mass',
    'traj_final_mass', 'traj_drag_coeff', 'traj_ref_area', 'traj_burn_time',
}


def test_p12bb112_motor_bandi_olan_her_alanda_tarayici_kapisi_var():
    bant = _motor_bantlari()
    eksik = sorted(k for k, (lo, hi) in _sayisal_girdiler().items()
                   if k in bant and (lo is None or hi is None))
    assert not eksik, (
        'ucun kabul bandı olduğu hâlde tarayıcı kapısı yok: ' + ', '.join(eksik))


def test_p12bb112_tarayici_kapisi_ucun_bandiyla_celismez():
    """HTML min/max, motorun kendi bandını AŞAMAZ (tek kaynak)."""
    bant = _motor_bantlari()
    celisen = []
    for k, (lo, hi) in _sayisal_girdiler().items():
        if k not in bant or lo is None or hi is None:
            continue
        blo, bhi = bant[k]
        if lo < blo - 1e-12 or hi > bhi + 1e-12:
            celisen.append(f'{k}: html[{lo}, {hi}] vs motor[{blo}, {bhi}]')
    assert not celisen, 'tarayıcı kapısı ucun kapısını temsil etmiyor: ' \
                        + '; '.join(celisen)


def test_p12bb112_bantsiz_alan_envanteri_buyumez():
    bant = _motor_bantlari()
    simdiki = {k for k, (lo, hi) in _sayisal_girdiler().items()
               if k not in bant and (lo is None or hi is None)}
    yeni = sorted(simdiki - BANTSIZ_ALANLAR)
    assert not yeni, (
        'ucun bandı olmayan yeni kapısız alan(lar) eklendi: ' + ', '.join(yeni))


# ===================================================================== #
# P12aB2-05 — terim tekliği                                             #
# ===================================================================== #
#: Türkçe metinde meşru kalan tek 'grain' geçişi: BATES yakıt bloğu
#: geometrisinin ÖZEL ADI. Diğer her geçiş 'yakıt bloğu' olmalıdır.
GRAIN_MUAFIYET = {
    'solid.ui.initial_diameter_of_the_central_core',  # 'BATES grain' özel adı
    'fx.s4.intro',            # 'yakıt bloğu (grain)' — terim parantezli açıklama
    'fx.s4_2.h',              # '4.2 Yakıt Bloğu (Grain) ...' — başlık parantezi
}


@pytest.mark.parametrize('dosya', [I18N_COMMON, I18N_PAGES, I18N_FORMULAS])
def test_p12ab205_tr_sozlukte_grain_kalintisi_yok(dosya):
    src = oku(dosya)
    kes = tr_bloklari(src)
    kalinti = []
    for m in re.finditer(r"^\s*'([\w.\-]+)':\s*'((?:[^'\\]|\\.)*)',?\s*$",
                         src[kes:], re.M):
        k, v = m.group(1), m.group(2)
        if k in GRAIN_MUAFIYET:
            continue
        if re.search(r'\bgrain\b', v, re.I):
            kalinti.append(k)
    assert not kalinti, (
        'TR sözlükte İngilizce "grain" kalıntısı (kanonik terim '
        '"yakıt bloğu"): ' + ', '.join(sorted(kalinti)))


def test_p12ab205_electron_payi_lule_sokuldu():
    """i18n_shell.js'teki iki 'lüle' kanonik 'nozul' terimine çevrildi."""
    src = oku(I18N_SHELL)
    assert 'lüle' not in src, 'i18n_shell.js hâlâ "lüle" diyor'
    assert src.count('nozul') >= 2, 'kanonik terim yerine konmamış'
