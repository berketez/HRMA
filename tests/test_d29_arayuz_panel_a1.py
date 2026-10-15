"""ÖH D29 · kulvar **arayuz-panel**, aşama 1 — onarım bekçileri.

Her iddia bir ÖLÇÜLMÜŞ kusura bağlıdır; ölçümler
``docs/scofield/raw/OH/D29/arayuz-panel/a1/{once,sonra}.json`` içinde,
ters-mutasyon kanıtları ``mutasyon.json`` içindedir.

Kapsanan kalemler
-----------------
* **OH-D28-03** — ``blowdown_panel.js`` sekiz dürüstlük alanını hiç
  basmıyordu (dize künye + dört BOOL bayrak + üç kesme sayısı).
* **OH-D28-04** — ``safety_panel.js`` basınç kabının geometrisini
  (``inner_diameter_mm`` / ``wall_thickness_mm``) hiç basmıyordu.
* **P12bB1-12** — ``liquid.html``in sayısal alanlarında HTML kapısı
  ucun kabul bandını temsil etmiyordu (kısmî onarım: uç bandı ÖLÇÜLEN
  üç alan).
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'


def _oku(rel):
    yol = KOK / rel
    assert yol.exists(), f'dosya yok: {yol}'
    return yol.read_text(encoding='utf-8')


def _yorumsuz(metin):
    """JS kaynağından ``//`` ve ``/* */`` yorumlarını siler.

    ÖLÇÜLDÜ (``a1/mutasyon.json``, ilk koşum): yorum süzülmeden yapılan
    tarama YALANCI YEŞİL veriyordu — ``FLAG_FIELDS``ten
    ``vapor_model_valid`` satırı SİLİNDİĞİ hâlde bekçi geçiyordu, çünkü
    ``blowdown_panel.js``in 202. satırındaki açıklama metni
    ```bd.vapor_model_valid``` dizgesini taşıyor ve metin tabanlı regex
    onu "okuma" sayıyordu. Bu, D27 dersi 11'in (metne bakan tarayıcı
    sözdizimine bakmaz) bu dosyadaki karşılığıdır: kanıtlanmak istenen
    şey KODUN alanı okuması, yorumun alandan söz etmesi değil.
    """
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', metin)


def _acik_okuma(metin, alan):
    """``x.<alan>`` biçiminde AÇIK özellik erişimi var mı? (yorumsuz)

    Dinamik ``x[ad]`` erişimi KABUL EDİLMEZ: ters-yön sözleşme bekçisinin
    okuma envanteri (``test_wave3_contract._envanter_metinden``) onu
    göremez, yani "panel bu alanı basıyor" iddiası kanıtlanamaz olurdu.
    """
    return bool(re.search(r'\.' + re.escape(alan) + r'(?![A-Za-z0-9_])',
                          _yorumsuz(metin)))


# --------------------------------------------------------------------------
# OH-D28-03 — blowdown_panel.js sekiz dürüstlük alanı
# --------------------------------------------------------------------------

#: Ucun ``motor.tank_blowdown`` bloğunda yayımladığı, D29 öncesi panelde
#: 0 kez geçen sekiz alan (``once.json`` OH-D28-03).
BLOWDOWN_DURUSTLUK_ALANLARI = (
    'tank_model_envelope_basis',
    'tank_saturation_band_clamped',
    'vapor_model_valid',
    'vapor_phase_integrated',
    'residual_oxidizer_kg',
    'residual_impulse_at_cutoff_rate_Ns',
    'residual_impulse_fraction_at_cutoff_rate',
    'vapor_tail_off_leaves_model_envelope',
)


@pytest.mark.parametrize('alan', BLOWDOWN_DURUSTLUK_ALANLARI)
def test_ohd2803_blowdown_paneli_durustluk_alanini_okuyor(alan):
    """Sekiz alanın sekizi de panelde AÇIK özellik erişimiyle okunmalı."""
    metin = _oku('hrma/static/js/blowdown_panel.js')
    assert _acik_okuma(metin, alan), (
        f'blowdown_panel.js `bd.{alan}` alanını AÇIK erişimle okumuyor; '
        'uç bu dürüstlük alanını yayımlıyor '
        '(hrma/engines/hybrid_rocket_engine.py) ve panel basmazsa '
        'kullanıcı yayımlanan eğrinin kenetli mi çözüm mü olduğunu '
        'göremez.')


def test_ohd2803_bayraklar_ad_ve_degerle_ayni_rozette():
    """BOOL bayraklar ROZETTE ad ile değeri BİRLİKTE basmalı.

    Ad+değer ölçütü (D28 bekci a1): değer kendi adının bölgesinde
    basılmazsa kullanıcı hangi alanı okuduğunu bilemez.
    """
    metin = _oku('hrma/static/js/blowdown_panel.js')
    assert "badge(b.field + ' ' + (b.value ? 'true' : 'false')" in metin, (
        'bayrak rozeti alan adını ve değerini aynı dizgede basmıyor')
    assert "badge(k.field + ' ' + k.value.toFixed(k.digits)" in metin, (
        'kesme payı rozeti alan adını ve değerini aynı dizgede basmıyor')


def test_ohd2803_bayrak_ve_kesme_tablolari_uydurma_deger_basmaz():
    """Alan yoksa satır da yok: ``typeof`` kapıları yerinde olmalı.

    Uydurma varsayılan (eksik bayrağı ``false``, eksik sayıyı ``0``
    saymak) sahte veridir; eski sunucu yanıtında alan hiç bulunmaz.
    """
    metin = _oku('hrma/static/js/blowdown_panel.js')
    assert "typeof v === 'boolean'" in metin, (
        'FLAG_FIELDS okuması bool kapısı taşımıyor')
    assert "typeof v === 'number' && isFinite(v)" in metin, (
        'CUTOFF_FIELDS okuması sonlu-sayı kapısı taşımıyor')


# --------------------------------------------------------------------------
# OH-D28-04 — safety_panel.js basınç kabı geometrisi
# --------------------------------------------------------------------------

@pytest.mark.parametrize('alan', ('inner_diameter_mm', 'wall_thickness_mm'))
def test_ohd2804_guvenlik_paneli_kap_geometrisini_basiyor(alan):
    """Kabın iki boyutu da ``pressureVesselBlock`` içinde basılmalı."""
    metin = _oku('hrma/static/js/panels/safety_panel.js')
    assert _acik_okuma(metin, alan), (
        f'safety_panel.js `press.{alan}` alanını basmıyor; panel beş '
        'basıncı gösterip hükmün GİRDİSİ olan geometriyi gizliyor.')


def test_ohd2804_birim_etiketi_milimetre():
    """Uç bloğu MİLİMETRE yayımlar; satır 'mm' etiketiyle basılmalı.

    Giriş formundaki ``wall_thickness`` alanı METRE'dir. Etiket
    yazılmazsa 5 mm ile 5 m aynı görünür — birim körlüğü.
    """
    metin = _oku('hrma/static/js/panels/safety_panel.js')
    for alan in ('inner_diameter_mm', 'wall_thickness_mm'):
        kalip = (r"addRow\(rows,\s*'" + alan + r"',\s*press\." + alan
                 + r"[^)]*'mm'\)")
        assert re.search(kalip, metin), (
            f'{alan} satırı `mm` birim etiketiyle basılmıyor')


# --------------------------------------------------------------------------
# P12bB1-12 — liquid.html HTML kapısı ucun bandını temsil eder
# --------------------------------------------------------------------------

def _html_kapisi(alan_id):
    metin = _oku('hrma/templates/liquid.html')
    m = re.search(r'<input[^>]*id="' + re.escape(alan_id) + r'"[^>]*>', metin)
    assert m, f'liquid.html içinde id="{alan_id}" alanı yok'
    etiket = m.group(0)
    alt = re.search(r'\bmin="([^"]*)"', etiket)
    ust = re.search(r'\bmax="([^"]*)"', etiket)
    return (float(alt.group(1)) if alt else None,
            float(ust.group(1)) if ust else None)


def test_p12bb112_mixture_ratio_kapisi_form_limits_ile_ayni():
    """``mixture_ratio`` HTML kapısı ucun FORM_LIMITS bandıyla aynı olmalı.

    TEK KAYNAK (doktrin 4): sayı iki yerde yazılıyor (Python sabiti ve
    HTML özniteliği); HTML'den import yapılamadığı için ayrışma BU
    bekçiyle yakalanır.
    """
    from hrma.validation.motor_validation import FORM_LIMITS
    alt, ust, _birim = FORM_LIMITS['liquid']['mixture_ratio']
    assert _html_kapisi('mixture_ratio') == (float(alt), float(ust))


def test_p12bb112_discharge_coefficient_kapisi_user_cd_range_ile_ayni():
    """``discharge_coefficient`` kapısı ``USER_CD_RANGE`` ile aynı olmalı."""
    from hrma.engines.injector_design import USER_CD_RANGE
    assert _html_kapisi('discharge_coefficient') == (
        float(USER_CD_RANGE[0]), float(USER_CD_RANGE[1]))


def test_p12bb112_characteristic_length_kapisi_l_star_bandi_ile_ayni():
    """``characteristic_length`` kapısı L* bandıyla (metre) aynı olmalı."""
    from hrma.engines.liquid_rocket_engine import L_STAR_MAX_M, L_STAR_MIN_M
    assert _html_kapisi('characteristic_length') == (
        float(L_STAR_MIN_M), float(L_STAR_MAX_M))


# --------------------------------------------------------------------------
# P12bB4-08 — /formulas model-farkı beyanı KUTUYA bağlıdır
# --------------------------------------------------------------------------

def _formulas():
    return _oku('hrma/templates/formulas.html')


def test_p12bb408_her_model_notu_bir_kutuya_bagli():
    """Her ``*.model_note`` beyanı, adını taşıyan bir kutuya bağlanmalı.

    ÖLÇÜLDÜ (``a1/once.json`` P12bB4-08): sayfada 143 formül kutusu var
    ve HİÇBİRİ hangi beyanın kendisini anlattığını söylemiyordu; beyan
    kutunun KARDEŞİ olan bir ``<div class="info">`` içindeydi ve eşleşme
    yalnız SIRAYA bağlıydı. Bir kutu araya girse ya da beyan taşınsa
    okuyucu yanlış kutuyu okurdu ve bunu hiçbir bekçi görmezdi.
    """
    metin = _formulas()
    notlar = set(re.findall(r'data-i18n="([\w.]+\.model_note)"', metin))
    assert notlar, 'sayfada hiç model farkı beyanı yok — ölçüm bayatlamış'
    bagli = set(re.findall(r'data-model-gap="([\w.]+)"', metin))
    assert notlar == bagli, (
        'model beyanı ile kutu bağlaması ayrıştı; beyanı olup kutusu '
        f'olmayan: {sorted(notlar - bagli)}, kutusu olup beyanı olmayan: '
        f'{sorted(bagli - notlar)}')


def test_p12bb408_toc_model_farki_uyarisi_duruyor():
    """§14'e yönlendiren içindekiler uyarısı silinmemeli (D28 arayuz a4)."""
    metin = _formulas()
    assert 'fx.toc.modelGapNotice' in metin
    assert 'href="#nasa-standards"' in metin


# --------------------------------------------------------------------------
# P12bB4-06 — /formulas §5.3 beyanı BAYATLAYAMAZ
# --------------------------------------------------------------------------

def test_p12bb406_soguutucu_beyani_urunun_sabitleriyle_ayni():
    """§5.3 beyanının saydığı üç sabit ürünle birebir aynı olmalı.

    Beyan YALAN OLAMAZ: ``fx.s5_3.model_note`` ürünün soğutucu tarafını
    hangi koşulda HESAPLADIĞINI (kanal girdileri verildiyse Dittus-Boelter)
    ve hangi koşulda MODELLEMEDİĞİNİ (girdiler yoksa beyan edilen tipik
    bant: 25 / 100 / 20000 W/m²K) söyler. Ürünün sayıları ya da sözleşmesi
    değişirse bu cümle sessizce yalana döner — bekçi onu KIRMIZI yapar.

    ÖH D31 / P12bB4-06 (termo-ucus a1) — BEKÇİ ÇEVRİLDİ: bu test eskiden
    üç sabiti ``_coolant_side_coefficient`` GÖVDESİNDE ``return 25.0``
    biçiminde arıyordu, yani sabitleri o gövdeye ÇİVİLİYORDU ve kusurun
    kendisini (korelasyon yerine sabit) koruyordu. Ürün ayağı onarıldı:
    sayılar artık tek kaynakta (``COOLANT_SIDE_DECLARED_TYPICAL``) durur ve
    YALNIZ ``coolant_side_method='not_modelled'`` künyesiyle yayımlanır.
    Bekçinin AMACI değişmedi (sayfa ile ürün aynı sayıyı söylemeli), ölçtüğü
    yer tek kaynağa taşındı.
    """
    from hrma.analysis.heat_transfer_analysis import (
        COOLANT_SIDE_DECLARED_TYPICAL)
    metin = _formulas()
    # ÖH D37 taban-onarım: D36 kabuk-elle (d1d81989, OH-K-01..05) HTML
    # taşıyan beyan düğümüne `data-i18n-html` işaretini ekledi (i18n.js
    # onu innerHTML ile yazar); açılış etiketi artık
    # `data-i18n="…" data-i18n-html>`. YALNIZ bu öznitelik isteğe bağlı
    # kabul edilir — desen başka hiçbir şeye gevşemez.
    m = re.search(r'data-i18n="fx\.s5_3\.model_note"(?: data-i18n-html)?>'
                  r'(.*?)</span>', metin, re.S)
    assert m, '§5.3 model farkı beyanı yok'
    beyan = m.group(1)
    sabitler = {f'{v:.0f}' for v in COOLANT_SIDE_DECLARED_TYPICAL.values()}
    assert sabitler == {'100', '20000', '25'}, (
        f'ürün sabitleri değişmiş: {sorted(sabitler)} — §5.3 beyanı '
        'güncellenmeli')
    for sayi in ('25', '100', '20000'):
        assert sayi in beyan, (
            f'§5.3 beyanı ürünün {sayi} W/m²K sabitini anmıyor')
    # Sabitin HANGİ KOŞULDA döndüğü de beyanda durmalı: onarımdan sonra bu
    # sayılar bir korelasyonun sonucu değil, "modellenmedi" künyesidir.
    assert 'not_modelled' in beyan, (
        '§5.3 beyanı sabitleri anıyor ama bunların not_modelled künyesiyle '
        'döndüğünü söylemiyor')
    assert 'dittus_boelter' in beyan, (
        '§5.3 beyanı, kanal girdileri verildiğinde korelasyonun GERÇEKTEN '
        'koşturulduğunu söylemiyor')
