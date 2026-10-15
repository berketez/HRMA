"""ÖH D29 · arayuz-panel aşama-2 bekçileri.

Kapsam (11 kalem): OH-D17-26, OH-Z1-07, P12bB4-11, P12bB4-12, P12bB4-13,
P12bS1-05, P12bS1-06, P16B1-38, P11B1-10, P11B1-11, P11B1-12.

Her iddia bir ÖLÇÜME dayanır (``docs/scofield/raw/OH/D29/arayuz-panel/a2/
once.json`` → ``sonra.json``) ve ters-mutasyonla kırmızı verdiği kanıtlanır
(``mutasyon.json``). Çürütülen kalemlerin bekçisi de vardır: çürütme
"baktım düzelmiş" değil, kusurun GERİ GELEMEYECEĞİNİN kilididir.
"""
import json
import os
import re
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def _yorumsuz_js(metin):
    """JS gövdesinden yorumları söker.

    D29 a1 dersi: bekçi yorum satırındaki bir sembolü "bağlanmış" sanabilir.
    Bütün sayımlar yorumsuz gövdede yapılır.
    """
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return re.sub(r'(?m)//.*$', '', metin)


def _yorumsuz_html(metin):
    return re.sub(r'(?s)<!--.*?-->', '', metin)


def _blok(metin, imza):
    """``function ad(`` imzasından süslü parantez dengesiyle biten gövde."""
    i = metin.find(imza)
    if i < 0:
        return None
    j = metin.find('{', i)
    if j < 0:
        return None
    derinlik, k = 0, j
    while k < len(metin):
        if metin[k] == '{':
            derinlik += 1
        elif metin[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
        k += 1
    return None


@pytest.fixture(scope='module')
def deck():
    return _oku('hrma/static/js/motor_viz_deck.js')


@pytest.fixture(scope='module')
def viz():
    return _oku('hrma/static/js/motor_viz3d.js')


@pytest.fixture(scope='module')
def formulas():
    return _oku('hrma/templates/formulas.html')


# ==========================================================================
# OH-D17-26 — efsanenin cidar beyanı DIŞ sıcaklık varken de basılır
# ==========================================================================

def test_ohd1726_beyan_dis_sicaklik_varken_susmaz(deck):
    """``wallTempNote`` yalnız İÇ sıcaklığa bakmalı, ikisinin VEYA'sına değil.

    ÖLÇÜLDÜ (a2/once.json OH-D17-26): erken çıkış
    ``info.tWallInner || info.tWallOuter`` idi. Katı motor
    (``solid_rocket_engine.py:12849``) ``inner_temperature``ı bile bile
    ``None`` yayımlıyor ve yanına yalnız ``outer_temperature`` + kaynak
    künyesini koyuyor; dış sayı geldiği için beyan tümden susuyordu.
    """
    govde = _blok(_yorumsuz_js(deck), 'function wallTempNote(')
    assert govde, 'wallTempNote bulunamadı'
    assert not re.search(r'info\.tWallInner\s*\|\|\s*info\.tWallOuter', govde), (
        'erken çıkış hâlâ iki sayının VEYA’sına bakıyor — dış sıcaklık '
        'gelince beyan yine susar')
    assert 'wallTempInnerMissing' in govde, (
        'iç cidarın çözülmediğini söyleyen dal yok')


def test_ohd1726_ic_yok_dis_var_dalinda_alan_adi_basilir(deck):
    """Dış sayı varken beyan, EKSİK olanın makine adını söylemeli."""
    g = _yorumsuz_js(deck)
    m = re.search(r"var wallTempInnerMissing\s*=\s*'([^']+)'", g)
    assert m, 'wallTempInnerMissing künyesi bir dize sabiti olmalı'
    assert 'inner_temperature' in m.group(1), (
        f'künye eksik alanı adıyla söylemiyor: {m.group(1)!r}')


def test_ohd1726_kaynak_kunyesi_iki_alani_da_okur(deck):
    """Künye üreticisi çözücünün iki beyan alanını da okumalı."""
    g = _yorumsuz_js(deck)
    kunye = _blok(g, 'function wallTempKunye(')
    assert kunye, 'wallTempKunye bulunamadı'
    for alan in ('wall_temperature_status', 'wall_temperature_source'):
        assert alan in kunye, f'{alan} okunmuyor'


def test_ohd1726_efsanedeki_slas_ic_sayiya_kosullu(deck):
    """İç cidar yokken satır ``/ outer …`` diye boş slaşla başlamamalı."""
    g = _yorumsuz_js(deck)
    assert re.search(r"info\.tWallInner \? ' / ' \+ TX\('outer'\)", g), (
        'ayırıcı slaş hâlâ koşulsuz — iç cidar çözülmediğinde satır '
        'öndeki boş slaşla başlar')


# ==========================================================================
# P11B1-10 — lüle cidarının uydurma oranı BEYAN EDİLİR
# ==========================================================================

def test_p11b110_uydurma_oran_beyansiz_kalamaz(viz):
    """Yedeğe düşen lüle cidarı ölçü kaynağı defterine girmeli.

    ÖLÇÜLDÜ (a2/once.json P11B1-10): ``nozzleWall`` çözücü değeri yokken
    ``max(3 mm; 0,10·d_t)`` yedeğinden çiziliyordu ve defterde satırı yoktu
    (``srcDecl_nozzle_wall: false``). O oran ürünün KENDİ söktüğü kuraldır:
    ``nozzle_design.py::_calculate_nozzle_geometry`` yorumu onu "hiçbir
    kaynağı yoktu" diye ilan edip hoop bağıntısıyla (Huzel & Huang,
    NASA SP-125 Böl. 4) değiştirmiştir.
    """
    g = _yorumsuz_js(viz)
    # Ters-mutasyon dersi: salt metin varlığı `if (false) decl(...)` ile
    # atlatılabiliyordu. Çağrı KENDİ BAŞINA bir deyim olmalı (girintili,
    # önünde koşul yok) — koşula alınırsa bekçi kırmızı verir.
    assert re.search(r"(?m)^\s+decl\('nozzle_wall',", g), (
        'lüle cidarı defterde beyan edilmiyor ya da beyan bir koşulun '
        'içine alınmış')
    # Yedek değer hâlâ çizilebilir (boş lüle bilgi vermez) ama artık
    # doğrudan `num(..., max(3, 0.1*dt))` yedeği olarak GİZLİ olamaz.
    assert not re.search(
        r'nozzleWall\s*=\s*clamp\(num\(md\.nozzle_geometry[^\n]*'
        r'Math\.max\(3,\s*0\.1\s*\*\s*dt\)', g), (
        'cidar hâlâ tek satırda sessiz yedeğe düşüyor')


def test_p11b110_beyan_hukmu_cozucu_degerine_bagli(viz):
    """Hüküm SABİTE değil, çözücünün gerçekten yayımladığına bağlı olmalı."""
    g = _yorumsuz_js(viz)
    assert re.search(
        r'nozzleWallKaynakli\s*=\s*isFinite\(nozzleWallSrc\)\s*&&\s*'
        r'nozzleWallSrc\s*>\s*0', g), (
        'kaynak hükmü ölçülmüyor (sabit true/false olamaz)')
    assert re.search(r"decl\('nozzle_wall',\s*nozzleWallKaynakli", g)


def test_p11b110_cip_etiketi_var(viz):
    """Beyan çipe ulaşmalı: defterde satır olup etiketi olmayan alan
    kullanıcıya HİÇBİR ŞEY söylemez (D26 'kanal var kapı yok' dersi)."""
    g = _yorumsuz_js(viz)
    assert re.search(r"nozzle_wall:\s*\[[^\]]*'nozzle wall'\]", g), (
        'DIM_SRC_LABEL_KEYS içinde nozzle_wall etiketi yok')


def test_p11b110_amber_cip_gercekten_ciktigi_node_ile_olculur(viz):
    """Uçtan uca: yedek hükümde çip DİZİSİ boş kalmamalı."""
    g = _yorumsuz_js(viz)
    parcalar = []
    for imza in ('var DIM_SRC_LABEL_KEYS = ', 'function srcNote(',
                 'function dimensionSourceChipDefs('):
        if imza.startswith('var '):
            i = g.find(imza)
            j = g.find('};', i)
            parcalar.append(g[i:j + 2])
        else:
            parcalar.append(_blok(g, imza))
    assert all(parcalar), 'çip kanalının parçaları bulunamadı'
    betik = ("function T(k, f) { return f; }\n" + '\n'.join(parcalar) + r"""
var yedek = { motorType: 'liquid', srcDecl: {
    chamber_diameter: { kind: 'computed' },
    nozzle_wall: { kind: 'assumed', basis: 'geometric fallback' } } };
var cozucu = { motorType: 'liquid', srcDecl: {
    chamber_diameter: { kind: 'computed' },
    nozzle_wall: { kind: 'computed' } } };
process.stdout.write(JSON.stringify({
    yedek: dimensionSourceChipDefs(yedek),
    cozucu: dimensionSourceChipDefs(cozucu) }));
""")
    ck = subprocess.run(['node'], input=betik, capture_output=True,
                        text=True, timeout=60)
    assert ck.returncode == 0, ck.stderr
    ciz = json.loads(ck.stdout)
    assert ciz['cozucu'] == [], 'çözücüden gelen cidar için çip basılmamalı'
    assert len(ciz['yedek']) == 1, 'uydurma cidar için tek amber çip beklenir'
    assert 'nozzle_wall' in ciz['yedek'][0]['fields']
    assert 'nozzle' in ciz['yedek'][0]['text']


# ==========================================================================
# P11B1-12 — extractDims'in okunmayan beyan alanları
# ==========================================================================

def _okunmayan_anahtarlar(viz, deck):
    ed = _blok(viz, 'function extractDims(')
    ri = ed.rfind('return {')
    anahtarlar = sorted(set(re.findall(
        r'(?m)^\s*([A-Za-z_$][\w$]*)\s*:', ed[ri:])))
    govde = _yorumsuz_js(viz + '\n' + deck).replace(_yorumsuz_js(ed), '')
    return [a for a in anahtarlar
            if not re.search(r'\.' + re.escape(a) + r'(?![\w$])', govde)]


def test_p11b112_hicbir_beyan_alani_okunmadan_kalmaz(viz, deck):
    """``extractDims`` sözlüğünün her alanı bir yerde TÜKETİLMELİ.

    ÖLÇÜLDÜ (a2/once.json P11B1-12): 41 alanın 2'si sahnede de güvertede de
    hiç okunmuyordu — ``injectorSource`` ve ``contourBasis``. Ham raporun
    saydığı 5 alandan üçü (``pc``, ``Rconv``, ``liner``) sonraki dalgalarda
    tüketilmiş; kalan ikisi kalemin BAŞLIĞIDIR ("hangi enjektörün çizildiğini
    söyleyecek olan beyan alanı").
    """
    kalan = _okunmayan_anahtarlar(viz, deck)
    assert kalan == [], (
        f'extractDims şu alanları hesaplayıp atıyor: {kalan}')


def test_p11b112_enjektor_beyani_cipe_bagli(viz):
    """``injectorSource`` bir DURUM ÇİPİNE bağlanmalı (defter değil: iki
    değer de çözücüden gelir, 'uydurma' değildir — kullanıcının bilmediği
    şey HANGİSİNİN çizildiğidir)."""
    g = _yorumsuz_js(viz)
    tanim = _blok(g, 'MotorScene.prototype._statusChipDefs = function (')
    assert tanim, '_statusChipDefs bulunamadı'
    assert re.search(r"(?m)^\s+if \(d\.injectorSource &&", tanim), (
        'enjektör beyanı çipe girmiyor ya da koşulu devre dışı bırakılmış')
    # i18n devri (arayuz-i18n): bu dalgada i18n_common.js kardeş kulvarın
    # elinde, bu yüzden çip metni ANAHTARSIZ makine dizesi olarak basılır
    # (künyenin kendisi zaten makine dizesi: 'injector_results' /
    # 'injector_design'). Anahtar sonraki aşamada bağlanacak.
    assert "'injector block: ' + d.injectorSource" in tanim, (
        'çip metni enjektör künyesini basmıyor')


def test_p11b112_enjektor_cipi_cizilmeyen_enjektor_icin_basilmaz(viz):
    """Enjektör hiç çizilmediyse kaynağı da beyan edilmez (sahte beyan
    yasağı: olmayan nesnenin künyesi kullanıcıyı yanıltır)."""
    g = _yorumsuz_js(viz)
    tanim = _blok(g, 'MotorScene.prototype._statusChipDefs = function (')
    assert re.search(
        r'if \(d\.injectorSource && \(d\.nOrifices > 0 \|\| d\.injPattern\)\)',
        tanim), 'enjektör çipi çizim koşuluna bağlı değil'


def test_p11b112_kontur_kunyesi_cipte_gorunur(viz):
    """``contourBasis`` kontur çipinin metnine girmeli; künye yoksa
    parantez hiç açılmaz (uydurma künye yasak)."""
    g = _yorumsuz_js(viz)
    tanim = _blok(g, 'MotorScene.prototype._statusChipDefs = function (')
    assert tanim.count('d.contourBasis') >= 4, (
        'kontur künyesi iki dalın da metnine + basis alanına bağlanmalı')
    assert "d.contourBasis ? ' (' + d.contourBasis + ')' : ''" in tanim, (
        'künye yokken boş parantez basılıyor olabilir')


# ==========================================================================
# P12bB4-12 / P12bB4-13 — /formulas kutuları ürünün modelini söylüyor
# ==========================================================================

def test_p12bb412_iki_faz_kutusu_model_farkini_beyan_ediyor(formulas):
    """§13.2 kutusunun iki değişkeni üründe HİÇ yok — kutu bunu söylemeli.

    ÖLÇÜLDÜ (a2/once.json P12bB4-12): ``hrma/analysis/two_phase_loss.py``
    içinde ``phi`` 0 kez, ``xi`` 0 kez geçiyor; kutu ise Isp'yi bu iki
    değişkenle düşürüyormuş gibi duruyor.
    """
    m = _yorumsuz_html(formulas)
    assert 'data-model-gap="fx.s13_2.model_note"' in m, (
        '§13.2 kutusu model farkı beyanına bağlanmamış')
    # ÖH D37 taban-onarım: D36 kabuk-elle (d1d81989, OH-K-01..05) HTML
    # taşıyan beyan düğümüne `data-i18n-html` işaretini ekledi (i18n.js
    # onu innerHTML ile yazar); açılış etiketi artık
    # `data-i18n="…" data-i18n-html>`. YALNIZ bu öznitelik isteğe bağlı
    # kabul edilir — desen başka hiçbir şeye gevşemez.
    not_m = re.search(
        r'data-i18n="fx\.s13_2\.model_note"(?: data-i18n-html)?>(.*?)</span>',
        m, re.S)
    assert not_m, 'fx.s13_2.model_note metni yok'
    metin = not_m.group(1)
    # Beyan ÜRÜNÜN modelini adıyla söylemeli, "farklıdır" demekle yetinmemeli.
    for parca in ('two_phase_loss.py', 'Hermsen', 'd43'):
        assert parca in metin, f'beyan {parca!r} demiyor'


def test_p12bb412_urun_hala_phi_xi_kullanmiyor():
    """Beyan BAYATLAYAMAZ: ürün bir gün φ/ξ'ye geçerse bekçi kırmızı olur."""
    kaynak = _oku('hrma/analysis/two_phase_loss.py')
    for ad in ('phi', 'xi'):
        n = len(re.findall(r'(?<![A-Za-z0-9_])' + ad + r'(?![A-Za-z0-9_])',
                           kaynak))
        assert n == 0, (
            f'ürün artık {ad!r} kullanıyor ({n} kez) — §13.2 beyanı yalana '
            'döndü, metni güncelle')


def test_p12bb413_hibrit_regresyon_kutusu_aki_tabanini_beyan_ediyor(formulas):
    """§6.1 kutusu ``G_ox``, ürünün VARSAYILANI ``G_total`` — beyan şart.

    ÖLÇÜLDÜ (a2/once.json P12bB4-13): ``HybridRocketEngine`` kurucusunda
    ``flux_mode`` varsayılanı ``'total'``.
    """
    m = _yorumsuz_html(formulas)
    assert 'data-model-gap="fx.s6_1.model_note"' in m, (
        '§6.1 kutusu model farkı beyanına bağlanmamış')
    # ÖH D37 taban-onarım: D36 kabuk-elle (d1d81989, OH-K-01..05) HTML
    # taşıyan beyan düğümüne `data-i18n-html` işaretini ekledi (i18n.js
    # onu innerHTML ile yazar); açılış etiketi artık
    # `data-i18n="…" data-i18n-html>`. YALNIZ bu öznitelik isteğe bağlı
    # kabul edilir — desen başka hiçbir şeye gevşemez.
    not_m = re.search(
        r'data-i18n="fx\.s6_1\.model_note"(?: data-i18n-html)?>(.*?)</span>',
        m, re.S)
    assert not_m, 'fx.s6_1.model_note metni yok'
    metin = not_m.group(1)
    for parca in ('flux_mode', 'G_total', 'Marxman'):
        assert parca in metin, f'beyan {parca!r} demiyor'


def test_p12bb413_urun_varsayilani_hala_total():
    """Beyan bayatlayamaz: ürün varsayılanı değişirse bekçi kırmızı olur."""
    kaynak = _oku('hrma/engines/hybrid_rocket_engine.py')
    m = re.search(r"flux_mode\s*=\s*flux_mode if flux_mode in "
                  r"\('total', 'ox'\)\s*else\s*'(\w+)'", kaynak)
    assert m, 'flux_mode varsayılan ifadesi bulunamadı — ölçüm bayatladı'
    assert m.group(1) == 'total', (
        f"ürün varsayılanı artık {m.group(1)!r}; §6.1 beyanını güncelle")


def test_p12bb408_model_notu_kutu_baglamasi_hala_tam(formulas):
    """a1'in kurduğu değişmez: her ``*.model_note`` bir kutuya bağlı."""
    m = _yorumsuz_html(formulas)
    notlar = set(re.findall(r'data-i18n="([\w.]+\.model_note)"', m))
    bagli = set(re.findall(r'data-model-gap="([\w.]+)"', m))
    assert notlar == bagli, (
        f'beyanı olup kutusu olmayan: {sorted(notlar - bagli)}; '
        f'kutusu olup beyanı olmayan: {sorted(bagli - notlar)}')
    assert len(notlar) >= 5, (
        f'a2 iki yeni beyan ekledi, sayı 5’in altına düşemez: {len(notlar)}')


# ==========================================================================
# ÇÜRÜTÜLEN KALEMLERİN KİLİDİ
# ==========================================================================

# OH-Z1-07 (niteliksiz Isp, 1 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
# P12bB4-11 (iki şablon rotalı + bayat 1220 yok, 2 düğüm; _sablon_rotalari yardımcısıyla) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


def test_p11b111_sivi_guvertesi_of_oranini_gonderiyor():
    """P11B1-11 ÇÜRÜTÜLDÜ — sıvı güvertesi O/F'i ``of_ratio`` adıyla veriyor.

    ÖLÇÜLDÜ (a2/once.json P11B1-11): ``buildLiquidVizData`` içinde
    ``data.of_ratio = …`` ataması var ve güverte çipi bu alandan doğuyor.
    Alan adı önemlidir: güverte çipi ``mixture_ratio`` ile de DOĞAR ama
    değeri ``of_ratio``/``of_ratio_initial``ten okur — yalnız
    ``mixture_ratio`` göndermek ekrana uydurma ``O/F 2.00`` bastırırdı.
    """
    lq = _oku('hrma/templates/liquid.html')
    govde = _blok(lq, 'function buildLiquidVizData(')
    assert govde, 'buildLiquidVizData bulunamadı'
    assert re.search(r'data\.of_ratio\s*=', govde), (
        'sıvı güvertesi O/F oranını göndermiyor — çip ekranda yok')
    # Uydurma yok: atama koşullu olmalı (çözücü yayımlamadıysa çip doğmaz).
    assert re.search(r'if \(ofOran !== null\) data\.of_ratio = ofOran', govde), (
        'atama koşulsuz — çözücü O/F yayımlamasa da çip doğar')


def test_p11b111_guverte_cipi_deger_kaynagini_karistirmaz():
    """Çipin DOĞDUĞU alanlar ile DEĞERİNİ okuduğu alanlar ayrı kalmalı."""
    deck_m = _yorumsuz_js(_oku('hrma/static/js/motor_viz_deck.js'))
    kosul = re.search(
        r'isNum\(md\.of_ratio\)[^;]*isNum\(md\.mixture_ratio\)', deck_m, re.S)
    assert kosul, 'O/F çipinin doğuş koşulu değişmiş — ölçüm bayatladı'


# ==========================================================================
# P16B1-38 — kamara boyu ezmesi sessizce yutulamaz
# ==========================================================================

def test_p16b138_ezme_beyan_seridi_var():
    """Bant dışı ezme kullanılmadığında ekranda beyan olmalı.

    ÖLÇÜLDÜ (a2/once.json P16B1-38): ``chamber_length_source`` ve
    ``inputs_not_used`` advanced.html'de 0 kez okunuyordu; 500000 mm'lik
    ezmenin tek izi yanıttaki kaynak alanının ``grain_limited``e dönmesiydi
    ve o alan ekrana hiç ulaşmıyordu.
    """
    adv = _oku('hrma/templates/advanced.html')
    assert 'id="chamberLengthSourceDecl"' in adv, 'beyan şeridi yok'
    assert 'chamber_length_source' in adv, (
        'çözücünün hüküm alanı hâlâ hiç okunmuyor')


def test_p16b138_beyan_hesap_sonrasi_doluyor():
    """Şerit ana hesaba bağlı olmalı (elle koşturma gerektirmemeli)."""
    adv = _oku('hrma/templates/advanced.html')
    # Ters-mutasyon dersi: çıplak `_chamberLengthOverrideDecl(results)`
    # deseni işlevin KENDİ TANIM satırıyla da eşleşiyordu. Aranacak olan
    # ÇAĞRI yeridir.
    assert re.search(
        r'try \{ _chamberLengthOverrideDecl\(results\); \}', adv), (
        'beyan displayCalculationResults sarmalayıcısına bağlı değil')
    assert 'window.displayCalculationResults = function' in adv, (
        'hesap köprüsü kurulmuyor')
    govde = _blok(adv, 'function _chamberLengthOverrideDecl(')
    assert govde, '_chamberLengthOverrideDecl bulunamadı'
    # Ezme uygulandıysa ya da hüküm yoksa şerit BASILMAZ (kazanılmamış rozet).
    assert "kaynak === 'user_override'" in govde, (
        'ezme uygulandığında şerit yine basılıyor olabilir')
    assert 'if (!(istenenMm > 0)) return;' in govde, (
        'ezme girilmediğinde de şerit basılıyor olabilir')


def test_p16b138_beyan_hicbir_sayi_uretmiyor():
    """Şeritteki iki sayı da KAYNAĞINDAN gelmeli (uydurma yasak)."""
    govde = _blok(_oku('hrma/templates/advanced.html'),
                  'function _chamberLengthOverrideDecl(')
    assert 'motor.chamber_length' in govde, 'uygulanan değer yanıttan gelmiyor'
    assert "getElementById('chamber_length_override')" in govde, (
        'istenen değer formdan gelmiyor')
    # Yanıt sayı yerine başka bir şey verdiyse SAYI UYDURULMAZ: alan adı basılır.
    assert "'motor.chamber_length = '" in govde, (
        'sayı gelmediğinde alan adı basılmıyor — sessiz yedek riski')


def test_p16b138_ezme_alani_birimini_makinece_beyan_ediyor():
    """Alanın birimi yalnız etiket metninde değil, ``data-unit``te de olmalı.

    ÖLÇÜLDÜ: aynı yükte dört alan MİLİMETRE, ``initial_port_diameter``
    METRE gidiyor (şablon 4521-4522'de /1000 çeviriyor); hiçbir alan
    birimini makinece beyan etmiyordu (``data_unit_tasiyan_sayisi: 0``).
    """
    adv = _oku('hrma/templates/advanced.html')
    assert re.search(r'id="chamber_length_override"[^>]*data-unit="mm"', adv), (
        'ezme alanı birimini makinece beyan etmiyor')


# ==========================================================================
# P12bS1-06 — app.js küresel işlevlerinin gölgelenmesi (KİLİT)
# ==========================================================================

#: ÖH D30 · arayuz-panel a1 — GÖLGELEME SÖKÜLDÜ, KÜME BOŞALDI.
#:
#: D29 a2'de burada 6 adlık bir gölgelenme kümesi kilitliydi ve kalemin
#: "13 işlev / 646 satır (%25,6)" iddiası çürütülmüştü (ölçüm: 6 işlev,
#: 69 satır, %1,8). D30 a1'de ölçüm İKİNCİ BİR YOLLA yenilendi (girinti
#: yerine süslü parantez DERİNLİĞİ; D29 lesson 17): gerçek sayı **11
#: işlev / 446 satır (%11,2)** çıktı — girinti ölçüsü derin girintili beş
#: bildirimi kaçırıyordu. On birinin gövdesi ``app.js``ten söküldü
#: (kanıt: docs/scofield/raw/OH/D30/arayuz-panel/a1/{once,sonra}.json).
#:
#: Küme artık BOŞ ve öyle kalmalı. Sayı YÜKSELTİLMEDİ, ölçü küme
#: ilişkisine çevrildi (D27 dersi 11 / D29 dersi 16). Ayrıntılı bekçi:
#: tests/test_d30_arayuz_panel_a1.py::TestOHD2902Golgeleme.
GOLGELENEN_KURESELLER = set()


def _golgelenen_kume():
    app = _yorumsuz_js(_oku('hrma/static/js/app.js'))
    adv = _oku('hrma/templates/advanced.html')
    kuresel = set(re.findall(r'(?m)^function\s+([A-Za-z_$][\w$]*)\s*\(', app))
    satirici = set(re.findall(
        r'(?m)^\s{1,20}function\s+([A-Za-z_$][\w$]*)\s*\(', adv))
    return kuresel & satirici


def test_p12bs106_golgelenme_kumesi_buyumedi():
    """Yeni bir satır içi ikiz eklenirse bekçi görür.

    Mekanizma GERÇEK: app.js ``/advanced``ta satır içi betikten ÖNCE
    yükleniyor (ölçüldü: src konumu 25820, sonraki satır içi betik 30046),
    bu yüzden aynı adlı ``function`` bildirimi app.js'inkini EZER. D28
    arayuz a3 bunun bir KAPI KAYBI olduğunu ``showDesignConfig`` üstünde
    ölçüp kapatmıştı; bekçi o kaybın yeni bir adla geri gelmesini engeller.
    """
    kume = _golgelenen_kume()
    yeni = kume - GOLGELENEN_KURESELLER
    assert yeni == set(), (
        f'advanced.html app.js’in şu küresel işlevlerini YENİ gölgeliyor: '
        f'{sorted(yeni)} — her biri sessiz bir kapı kaybı adayıdır')


def test_p12bs106_olcum_bayatlamadi():
    """Gölgelenme D30 a1'de söküldü — küme boş kalmalı.

    (D29'da bu bekçi "kalkan gölgeleme ölçümü bayatlatır" diyordu; D30 a1
    sökümünden sonra ölçüm YENİLENDİ ve küme boşaltıldı. Bekçi ters yöne
    çevrildi: gölgeleme GERİ GELİRSE kırmızı olur.)
    """
    kume = _golgelenen_kume()
    assert kume == GOLGELENEN_KURESELLER, (
        f'gölgeleme geri geldi: {sorted(kume)} — advanced.html satır içi '
        'betiği app.js işlevlerini yeniden bildiriyor')


def test_p12bs106_buyukluk_iddiasi_olculur():
    """Erişilemez pay ölçülür; D30 a1 sökümünden sonra 0 olmalı.

    Kalemin "%25,6 / 646 satır" iddiası D30 a1'de %11,2 / 446 satır olarak
    ölçüldü ve o 446 satır söküldü. Eşik değil GERÇEK sayı bekçisi: pay
    sıfırdan büyürse yeni bir ölü kopya girmiş demektir.
    """
    app = _oku('hrma/static/js/app.js')
    toplam = app.count('\n') + 1
    golge_satir = sum(
        (_blok(app, 'function ' + ad + '(') or '').count('\n') + 1
        if _blok(app, 'function ' + ad + '(') else 0
        for ad in _golgelenen_kume())
    oran = 100.0 * golge_satir / toplam
    assert golge_satir == 0, (
        f'app.js’te erişilemez {golge_satir} satır (%{oran:.1f}) var — '
        'gölgelenen gövdeler D30 a1’de sökülmüştü')


def test_p12bs106_yukleme_sirasi_hala_golgelemeye_izin_veriyor():
    """Mekanizmanın ön koşulu: app.js satır içi betikten ÖNCE yükleniyor."""
    adv = _oku('hrma/templates/advanced.html')
    app_konum = next(
        (m.start() for m in re.finditer(r'<script[^>]*src="([^"]+)"', adv)
         if m.group(1).endswith('/app.js')), None)
    assert app_konum is not None, 'advanced.html app.js yüklemiyor'
    sonraki = [m.start() for m in
               re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>', adv)
               if m.start() > app_konum]
    assert sonraki, (
        'app.js’ten sonra satır içi betik kalmamış — gölgelenme mekanizması '
        'ortadan kalkmış olabilir, ölçümü yenile')
