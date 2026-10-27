"""JS katmanının çift dilliliği — i18n_common.js sözlüğü ve kullanım testleri.

Kapsam (T-JS dalgası, 2026-07-19). tests/test_i18n.py çekirdek sözleşmeyi
(register kalıbı, EN/TR anahtar eşitliği, ASCII kaçışı, emoji) kilitler;
bu dosya KULLANIM tarafını kilitler:

  1. Sözdizimi: dokunulan her JS dosyası `node --check` geçer.
  2. İki yönlü tutarlılık:
     - Kodda çağrılan HER anahtar sözlükte VAR (yazım hatası koruması).
       Kapsam ÖH D33-3 / OH-D33-32'de genişledi: `hrma/static/js` + sayfa
       şablonlarının `data-i18n` nitelikleri (`KULLANIM`). Şablonda
       çağrılıp sözlüksüz kalan anahtar TR kipinde İNGİLİZCE basılır ve
       eski kapsam onu göremiyordu (ölçülen kurban `fx.s8_2.model_note`).
     - Sözlükteki HER anahtar kodda KULLANILIYOR (ölü çeviri koruması).
       Bu yönün ölçütü DEĞİŞMEDİ (`USED` + `SABLON_KULLANIMI`).
  3. Dil değişimi: güverte ve kendi DOM'unu kuran paneller I18N.onChange
     ile kendini yeniden basıyor (dil değişince ekran anında Türkçeleşir).
  4. Güverte sözleşmesi: panel başlıkları titleKey taşır, alan etiketleri
     5. eleman olarak anahtar taşır, kategori sekmelerinin dock.cat.*
     karşılığı sözlükte vardır.
  5. Kalıntı avı (dar heuristik): panellerde U.sectionTitle / U.listBlock /
     U.statCard çağrılarına DÜZ metin geçilmiş mi.

Heuristikler bilinçli olarak dardır: yanlış pozitif üretmemeleri, gerçek
regresyonu yakalamaları beklenir. Yeni bir yanlış pozitif çıkarsa çağrıyı
düzeltin; heuristiği gevşetmek denetimi kör eder.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
DICT_JS = STATIC_JS / 'i18n_common.js'

# ---------------------------------------------------------------------------
# Kapsam — ÖH FAZ D / D4 (defter P13B4-07, P13B4-08; sıra kısıtı K3)
# ---------------------------------------------------------------------------
# Bu dosyada hastalık ve ilaç yan yana duruyordu: `MODULE_FILES` ELLE
# yazılmış 19 dosyaydı, bir satır altındaki `PANEL_FILES` ise glob'dan
# TÜRETİLMİŞti. Aradaki boşluğa düşen dosya hiçbir i18n bekçisi tarafından
# görülmüyordu — ölçülen kurban `blowdown_panel.js` (551 satır, 23 anahtar):
# bir panel, ama `panels/` altında değil üst düzeyde durduğu için glob onu
# görmüyor, elle liste de saymamıştı. Yan etki: dosya `node --check`
# sözdizimi denetiminden de muaftı.
#
# Artık kapsam da türetiliyor. Ölçüt tek cümle: **çeviri anahtarını
# KULLANAN her JS dosyası taranır; anahtarı TANIMLAYAN sözlük kaynakları
# taranmaz.** Sözlük kaynağı mekanik olarak ayırt edilir (I18N.register
# çağırır) — elle muafiyet listesi yoktur.
#
# Sözlük kaynaklarının kapsam DIŞI kalması zorunludur: i18n_common.js'in
# kendi anahtar literalleri FIELD_RE'ye uyar, taransaydı her anahtar kendi
# kendini "kullanılıyor" ilan ederdi ve ölü-çeviri bekçisi vakumlanırdı
# (bkz. test_olu_ceviri_bekcisi_vakumlanmadi).

#: Elle liste döneminin kapsamı — TABAN (türetme daralırsa kırmızı).
#: Listenin kendi kaydettiği İKİ tarihsel çürüme vakası (P13B4-08) burada
#: korunuyor, çünkü elle listenin neden bırakıldığının kanıtıdır:
#:   2026-08-15  thermal_fea_panel.js listeye girmeseydi 48 anahtar
#:               "kullanılmıyor" sanılacaktı (ölçülmüş).
#:   2026-08-16  analysis_center.js listeye girmeseydi 49 anahtar
#:               "ölü çeviri" sayılacaktı (ölçülmüş).
#: Üçüncü çürüme artık doğamaz: yeni üst düzey js kapsama kendiliğinden girer.
TARIHSEL_MODULE_FILES = (
    'app.js', 'analysis_dock.js', 'injector_panel.js', 'injector_schematics.js',
    'sixdof_panel.js', 'transient_panel.js', 'update_check.js',
    'chart_captions.js', 'motor_viz3d.js', 'fea_panel.js',
    'thermal_fea_panel.js', 'motor_viz_deck.js', 'hud.js',
    'materials_catalog.js', 'propellant_catalog.js', 'import_ui.js',
    'project_bar.js', 'step_import_ui.js', 'analysis_center.js',
)

#: Üst düzey JS'in tamamı (türetilmiş).
TOP_LEVEL_JS = sorted(STATIC_JS.glob('*.js'))


def _sozluk_kaynagi(path):
    """Dosya çeviri anahtarı TANIMLIYOR mu?

    Ölçüt: `I18N.register(` çağırmak. Bu, sözlük dosyalarının yanı sıra
    kayıt motorunun kendisini (`i18n.js`) de seçer — o da kendi sözlük
    gövdesini taşıdığı için doğru sınıflandırmadır. Ölçütün aşırı dışlama
    yapmadığı ayrıca denetlenir (bkz.
    :func:`test_olu_ceviri_bekcisi_vakumlanmadi`): dışlanan her dosyada
    gerçek bir `DICT = {` gövdesi bulunmalıdır.
    """
    return 'I18N.register(' in path.read_text(encoding='utf-8')


#: Anahtar tanımlayan dosyalar — kullanım taramasının dışında (ölçüldü: 8).
SOZLUK_KAYNAKLARI = tuple(p for p in TOP_LEVEL_JS if _sozluk_kaynagi(p))

#: Çeviri anahtarını KULLANAN üst düzey modüller — türetilmiş (index.html
#: hariç; o şablon testi tests/test_i18n.py içinde).
MODULE_FILES = [p for p in TOP_LEVEL_JS if p not in SOZLUK_KAYNAKLARI]
PANEL_FILES = sorted(PANELS_DIR.glob('*.js'))
#: Kullanım taramasının kapsamı.
ALL_FILES = MODULE_FILES + PANEL_FILES
#: Sözdizimi denetiminin kapsamı — sözlük kaynakları DAHİL her JS dosyası.
#: (P13B4-07 yan etkisi: `blowdown_panel.js` bugüne dek `node --check`ten
#: de muaftı; artık değil.)
SYNTAX_FILES = TOP_LEVEL_JS + PANEL_FILES

#: Kapsama YENİ giren dosyalar (elle liste döneminde taranmayanlar).
YENI_KAPSAM = frozenset(p.name for p in ALL_FILES) - (
    frozenset(TARIHSEL_MODULE_FILES) | frozenset(p.name for p in PANEL_FILES))

#: D4 kapsam genişlemesinin AÇTIĞI çeviri borcu — K3'ün adıyla saydığı iki
#: aile. Borç yalnız bu iki ön ekle sınırlıdır: başka bir ön ekte sözlüksüz
#: anahtar çıkarsa (yeni dosya, yazım hatası) normal bekçi KIRMIZI verir,
#: borç imi onu yutmaz. Ödeme K3 sırasına bağlıdır ve ÜRÜN işidir
#: (`hrma/static/js/i18n_*.js` — bu paketin yazma yetkisi dışında).
# ÖH D27 / arayuz a2 (P12aB1-02) — ÇEVİRİ BORCU KAPANDI, AİLE BOŞALDI.
# Bu demet D4 kapsam genişlemesinin açtığı çeviri borcunu ADIYLA
# taşıyordu: 52 `shell.*` + 18 `blowdown.*` = 70 anahtar sözlükte yoktu
# ve `test_every_used_key_exists_in_dictionary` onları KAPSAM DIŞI
# bırakıyordu. Ölçüldü (bu depo, D27 a2): `_sozlukte_olmayanlar()` = **0**
# — `shell.*` ayağı ara dalgalarda, `blowdown.*` ayağı bu aşamada
# (18 anahtar + 6 künye etiketi, EN ve TR bloklarının içine) kapandı.
# Demet BOŞALTILDI ki ana bekçinin kapsamındaki DELİK de kapansın: artık
# sözlüksüz HER anahtar `test_every_used_key_exists_in_dictionary`te
# kırmızı verir, "borç ailesi" bahanesiyle sessizce geçemez.
CEVIRI_BORCU_AILELERI = ()

# Güvertenin kategori sekmeleri (panels/*.js `category:` alanları)
DOCK_CATEGORIES = [
    'THERMAL', 'STRUCTURAL', 'SAFETY', 'PERFORMANCE', 'FLOW', 'VALIDATION',
    'PRESSURE VESSEL', 'FEED SYSTEM', 'COMPARE', 'CORRELATION', 'UNCERTAINTY',
]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def read(path):
    return path.read_text(encoding='utf-8')


def strip_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur)."""
    def blank(match):
        return re.sub(r'[^\n]', ' ', match.group(0))

    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    out = []
    for line in text.split('\n'):
        quote = None
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch in '\'"`':
                    quote = ch
                elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        out.append(line if cut is None else line[:cut] + ' ' * (len(line) - cut))
    return '\n'.join(out)


def dict_block(lang):
    """i18n_common.js içindeki bir dil bloğunun (anahtar -> değer) sözlüğü."""
    source = read(DICT_JS)
    start = source.index('        %s: {' % lang)
    depth = 0
    for idx in range(start + len('        %s: ' % lang), len(source)):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                body = source[start:idx]
                break
    else:                                   # pragma: no cover - bozuk dosya
        pytest.fail("i18n_common.js '%s' bloğu kapanmıyor" % lang)
    pairs = re.findall(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',?\s*$",
                       body, re.M)
    return {k.replace("\\'", "'"): v.replace("\\'", "'") for k, v in pairs}


EN = dict_block('en')
TR = dict_block('tr')


def _diger_parca_anahtarlari():
    """i18n_common.js DIŞINDAKİ sözlük parçalarında tanımlı anahtarlar.

    ÖH D17 / electron a1 — bekçi ÇEVRİLDİ (gerekçe):
    i18n.js'in kendi başlığı sözlüğü ÇOK-PARÇALI ilan eder ve `register()`
    her parçayı aynı tabloya birleştirir; hangi parçada tanımlandığı ürün
    davranışını hiç değiştirmez. Bu dosyadaki `_sozlukte_olmayanlar()` ise
    yalnız i18n_common.js'i sözlük sayıyordu, yani i18n_shell.js'te tanımlı
    bir anahtarı "sözlükte yok" diye kırmızıya çeviriyordu. Sonuç, her yeni
    anahtarı tek bir dosyaya zorlamaktı — P12aB5-01'in D16'da onarılamamasının
    sebebi tam olarak buydu (47 `shell.bug.*` anahtarı Türkçesiz kaldı, rıza
    beyanı dâhil; onarım "i18n anahtar dosyaları Do-not-edit" kilidine
    takıldı). Ölçüt artık dosyanın kendi kavramını kullanıyor:
    SOZLUK_KAYNAKLARI. Bu, kapsamı GEVŞETMEZ — sözlük kaynağı olmayan bir
    dosyada tanımlı hiçbir şey sayılmaz, yazım hatası hâlâ kırmızı verir.
    """
    anahtarlar = set()
    for parca in SOZLUK_KAYNAKLARI:
        if parca == DICT_JS:
            continue
        metin = parca.read_text(encoding='utf-8')
        anahtarlar |= set(re.findall(
            r"^\s*'((?:[^'\\]|\\.)*)':\s*'", metin, re.M))
    return {k.replace("\\'", "'") for k in anahtarlar}


#: Başka parçalarda tanımlı anahtarlar (ölçüm anında türetilir).
DIGER_PARCALAR = _diger_parca_anahtarlari()

#: i18n_common.js'te ÖLÜ kalmış ama halefi başka parçada YAŞAYAN anahtarlar.
#: ÖH D17 / electron a1 (P12aB3-02): `chartCap.injector_plot` metni delik
#: YERLEŞİMİNİN basınç düşümünü "belirlediğini" söylüyordu; ölçüm hole_pattern
#: değişiminin 26 sayısal alanın 0'ını oynattığını gösterdi. `register()`
#: "ilk kazanır" dediği için metin yerinde ezilemiyordu ve i18n_common.js bu
#: dalgada arayüz kulvarının sahasındaydı; anahtar yeniden adlandırılıp
#: düzeltilmiş metin i18n_shell.js'e yazıldı. Eski girdinin SİLİNMESİ arayüz
#: kulvarına devredildi — burada adıyla, halefiyle ve gerekçesiyle duruyor.
DEVREDILEN_OLU_ANAHTARLAR = {
    'chartCap.injector_plot': 'chartCap.injectorFace',
}

# Kodda anahtar geçebilecek tüm biçimler:
#   T('key', ...) / TF('key', ...) / U.t('key', ...) / U.tf('key', ...)
#   data-i18n="key" / data-i18n-title="key" / data-i18n-placeholder="key"
#   titleKey: 'key' / key: 'key' / labelKey dizisi 5. elemanı / 'dock.cat.' + cat
CALL_RE = re.compile(r"(?:\bT|\bTF|U\.t|U\.tf|window\.I18N\.t|window\.I18N\.tf)"
                     r"\(\s*'([\w. ]+)'")
ATTR_RE = re.compile(r'data-i18n(?:-title|-placeholder)?="([\w. ]+)"')
# 2026-08-17 (parti 30): 'viz3d' ön eki listede YOKTU. 3B sahnenin CFD alan
# katmanı anahtarlarını TABLOLARDA tutar (motor_viz3d.js CFD_METRICS.labelKey
# ve CFD_REASONS[kod].key) ve çalışma anında DEĞİŞKENLE çözer:
#   sahne   motor_viz3d.js:4283  T(m.labelKey, m.labelFallback)
#   tüketen motor_viz_deck.js:153 / cfd_panel.js:1307
#           T(reason.key, reason.fallback)  — anahtar sahneden GELİR
# Yani anahtar çağrı yerinde literal olarak geçmez; CALL_RE onu yapısal olarak
# göremez. ÖLÇÜLDÜ: 9 canlı anahtar (6 red kodu + 3 metrik etiketi) "ölü
# çeviri" diye işaretleniyordu. Bu, 'status' öneki için 2026-08-03'te ölçülen
# kusurun aynısıdır: ön ek listesi ürünün GERÇEKTEN kullandığı ad alanlarını
# yansıtmalı, yoksa bekçi doğru eklemeyi engeller. Ölü çeviri koruması
# zayıflamaz — hiçbir kaynakta literal olarak geçmeyen anahtar hâlâ yakalanır.
# ÖH D18 / P12aB4-08: 'stepimp' ön eki listede YOKTU. STEP ölçü eşleme
# ekranının alan etiketleri `step_import_ui.js` SUGGESTION_KEYS dizisinde
# ÇIPLAK DİZE olarak yaşar (`['throat_diameter_mm', 'stepimp.fieldThroat',
# 'Throat diameter (mm)']`), yani CALL_RE onları yapısal olarak göremez.
# ÖLÇÜLDÜ: beş anahtar (fieldThroat/fieldExit/fieldChamberD/fieldChamberL/
# fieldWall) HİÇBİR sözlükte tanımlı değildi ve TR kipinde İngilizce
# basılıyordu; bu bekçi ise 3 passed veriyordu. 'status' (2026-08-03) ve
# 'viz3d' (2026-08-17) ile aynı kusurun üçüncü örneği: ön ek listesi ürünün
# GERÇEKTEN kullandığı ad alanlarını yansıtmalı, yoksa bekçi doğru eklemeyi
# de engeller. Ölü çeviri koruması zayıflamaz.
FIELD_RE = re.compile(r"'((?:common|panel|inj|sixdof|sch|out|uq|tps|vessel|joint|"
                      r"nzl|fuel|fluid|gas|coolant|cool|fac|motor|prop|press|mat|"
                      r"transient|update|app|dock|risk|chartCap|ac|viz3d|"
                      r"stepimp)\.[\w.]+)'")


# FIELD_RE yalnız yardımcı bir tarayıcıdır (alan dizilerindeki çıplak anahtar
# metinleri). Aynı desene uyan ama çeviri anahtarı OLMAYAN dizeler burada
# elenir — listeyi dar tutun, gerçek anahtar eklemeyin.
NOT_KEYS = {
    'motor.eng',          # app.js: .eng dosya adı
    # Z4 (2026-08-27): structural_panel ipucu sütunundaki düz MAKİNE-YOLU
    # dizesi — çeviri anahtarı değil, alan adresi (tasarlanmış kaçış kapısı).
    'motor.structural_analysis.safety_analysis.minimum_safety_factor',
    # ÖH D15 / P11B2-03 (ui-paneller a1): app.js lüle açıları bloğunun
    # `source`/`basis` alanlarındaki MAKİNE-YOLU dizesi — çeviri anahtarı
    # değil, çözücü alan adresi (aynı kaçış kapısı).
    'motor.nozzle_angles',
}


def used_keys():
    """Kodda geçen tüm çeviri anahtarları (dosya adlarıyla birlikte)."""
    found = {}
    for path in ALL_FILES:
        src = strip_comments(read(path))
        for regex in (CALL_RE, ATTR_RE, FIELD_RE):
            for match in regex.finditer(src):
                key = match.group(1)
                if key in NOT_KEYS or key.endswith('.'):
                    continue          # 'dock.cat.' + cat gibi ön ek parçaları
                found.setdefault(key, set()).add(path.name)
    # Güverte kategori sekmeleri dinamik kurulur ('dock.cat.' + cat)
    for cat in DOCK_CATEGORIES:
        found.setdefault('dock.cat.' + cat, set()).add('analysis_dock.js')
    # Sunucudan gelen uyarı kodları (aşağıdaki açıklamaya bakın)
    for key, kaynak in python_dispatched_keys().items():
        found.setdefault(key, set()).update(kaynak)
    return found


#: Çeviri anahtarı biçimi: en az iki nokta-ayrık parça, harf/rakam/alt çizgi.
# 2026-08-03 (Faz 6, T31): 'status' ön eki listede YOKTU. Doğrulama durumu
# kodları (status.critical / status.warnings / status.normal) tam da bu yolla
# üretiliyor — hrma/validation/validation_system.py:245-249 — ama tarama onları
# görmediği için sözlüğe eklenmeleri "ölü çeviri" sayılıyordu. Ön ek listesi
# Python'ın GERÇEKTEN gönderdiği ad alanlarını yansıtmalı, yoksa bekçi doğru
# eklemeyi engeller.
#: v3.0.1 (26 Eki, V301/H3 birleşmesi): ``info`` öneki eklendi. H3, sunucunun
#: ürettiği ilk BİLGİ düzeyli kodu getirdi (``info.injector.saturated_inlet_two_phase``,
#: ``hrma/utils/injector_design.py`` SATURATED_INLET_NOTE_CODE; EN + TR sözlükte).
#: Kod Python'da literal duruyor ama önek listesi onu görmediği için anahtar
#: "ölü" sayılıyordu — warn.* ile aynı yanlış pozitif sınıfı.
PY_KEY_RE = re.compile(
    r"['\"]((?:warn|info|panel|common|risk|out|status)\.[\w.]+)['\"]")


def python_dispatched_keys():
    """Python motorlarının ürettiği, JS'in ÇALIŞMA ANINDA gönderdiği anahtarlar.

    v2.6.25 — NEDEN BU FONKSİYON VAR:
    ``test_every_dictionary_key_is_used`` 213 anahtarı "kullanılmıyor" diye
    kırılıyordu. Ölçüldü: 213'ün **210'u Python kaynaklarında literal olarak
    duruyor** ve gayet de kullanılıyor. Kopukluk şurada:

        Python  hrma/engines/cycle_power_balance.py:1120
                'warn.cycle.ffsc_shaft_balance_infeasible' kodunu üretir
        JS      analysis_dock.js:192
                TF(w.code, p, ...) — anahtar SUNUCUDAN gelir, kaynakta
                literal olarak GEÇMEZ

    Yani anahtar JS dosyalarında hiçbir zaman yazılı olmaz; statik tarama onu
    yapısal olarak göremez. Testin eski hâli bu yüzden gerçek bir ölü-çeviri
    denetimi değil, yanlış pozitif üretecidir — ve 210 canlı anahtarı silmeye
    davet ediyordu.

    Burada Python tarafı da taranır: motorların ürettiği kod literalleri
    "kullanılıyor" sayılır. Ölü çeviri koruması korunur — ne JS'te ne
    Python'da geçmeyen anahtar hâlâ yakalanır (o denetim gerçekten çalışıyor:
    bu düzeltme sırasında 3 gerçek öksüz anahtar bulup sildik).
    """
    found = {}
    for path in (REPO_ROOT / 'hrma').rglob('*.py'):
        try:
            src = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):       # pragma: no cover
            continue
        for match in PY_KEY_RE.finditer(src):
            found.setdefault(match.group(1), set()).add(path.name)
    return found


#: Şablon (``hrma/templates/*.html``) kaynaklarında LİTERAL geçen anahtarlar.
#: Yalnız ÖLÜ ÇEVİRİ yönünde kullanılır — bkz. :func:`sablon_kullanimi`.
SABLON_ANAHTAR_RE = re.compile(r"""['"](\w+(?:\.\w+)+)['"]""")


def sablon_kullanimi():
    """Sayfa şablonlarının doğrudan yazdığı çeviri anahtarları.

    ÖH D24 / fix-22 — ÖLÇÜLEN KÖR NOKTA. Kullanım taraması yalnız
    ``hrma/static/js`` altını görüyor; sayfa şablonlarının İÇİNDEKİ JS
    (``liquid.html``, ``solid.html`` …) kapsam dışında. D23 (OH-D18-10 ve
    P16B2-06) üç panel uyarısını ``warn.*`` ad uzayından ``panelwarn.*``a
    taşıdı ve kodları ŞABLONDA üretiyor:

        hrma/templates/liquid.html:5890  code: 'panelwarn.liquid.valve_regime_not_verified'
        hrma/templates/liquid.html:5905  code: 'panelwarn.liquid.roughness_provenance_undeclared'
        hrma/templates/solid.html:2582   code: 'panelwarn.solid.nozzle_thermal_not_evaluated'

    Üç anahtar da CANLI, ama tarama şablonu görmediği için ölü-çeviri
    bekçisi onları "kullanılmıyor" sayıyordu (ölçüldü: taban kaydı-7,
    3/8 yanlış pozitif). Bu, ``python_dispatched_keys``in kapattığı
    kusurun aynısıdır: anahtar ÜRÜNDE yaşıyor ama tarama onu göremiyor.

    Kapsam bilerek DARDIR: burada toplanan küme yalnız
    ``test_every_dictionary_key_is_used`` (ölü çeviri) yönünde sayılır,
    "kullanılan anahtar sözlükte var mı" yönünde SAYILMAZ — şablonlar
    kendi sözlüklerinden (``i18n_pages.js``, ``i18n_advanced.js``)
    beslenir ve o yön ``tests/test_i18n.py``nin konusudur. Böylece ölü
    çeviri koruması zayıflamaz: hiçbir kaynakta (JS + Python + şablon)
    literal olarak geçmeyen anahtar hâlâ yakalanır.
    """
    found = {}
    dizin = REPO_ROOT / 'hrma' / 'templates'
    for path in sorted(dizin.glob('*.html')):
        try:
            src = read(path)
        except (OSError, UnicodeDecodeError):       # pragma: no cover
            continue
        for match in SABLON_ANAHTAR_RE.finditer(src):
            found.setdefault(match.group(1), set()).add(path.name)
    return found


def sablon_data_i18n_kullanimi():
    """Şablonların ``data-i18n`` nitelikleriyle ÇAĞIRDIĞI anahtarlar.

    ÖH D33-3 / OH-D33-32 — ÖLÇÜLEN KAPSAM BOŞLUĞU.
    ``test_every_used_key_exists_in_dictionary`` (yazım hatası koruması)
    yalnız ``hrma/static/js`` altını tarıyordu. Oysa ``I18N.apply()``
    ekrana çizerken ``[data-i18n]`` düğümlerini de çözer: şablonda
    kullanılıp HİÇBİR sözlükte tanımlı olmayan bir anahtar, TR kipinde
    satır-içi İNGİLİZCE metnin ekranda kalması demektir — ve bekçi bunu
    görmüyordu.

    ÖLÇÜLEN KURBAN (Opus uç denetimi v2, arayuz-04, 16 Eylül 2026):
    ``fx.s8_2.model_note`` ``formulas.html``te kullanılıyordu, hiçbir
    sözlükte yoktu; TR kullanıcı modelin dürüstlük notunu İngilizce
    okuyordu. Bu bekçi o gün ``passed`` veriyordu. Borcu fix-37c ödedi;
    kapsam boşluğu BURADA kapanıyor.

    ``sablon_kullanimi`` ile karıştırmayın: o, ŞABLONDA LİTERAL geçen her
    noktalı dizeyi toplar ve yalnız ÖLÜ ÇEVİRİ yönünde sayılır (kapsamı
    geniş, ölçütü gevşek). Bu fonksiyon yalnız ``data-i18n`` niteliğini
    okur — yani şablonun gerçekten "bu düğümü sözlükten çiz" dediği
    yerleri — ve KULLANIM yönünde sayılır.
    """
    found = {}
    for path in sorted((REPO_ROOT / 'hrma' / 'templates').glob('*.html')):
        try:
            src = read(path)
        except (OSError, UnicodeDecodeError):       # pragma: no cover
            continue
        for match in ATTR_RE.finditer(src):
            found.setdefault(match.group(1), set()).add(path.name)
    return found


USED = used_keys()
SABLON_KULLANIMI = sablon_kullanimi()
#: Şablonların ``data-i18n`` ile çağırdığı anahtarlar (OH-D33-32).
SABLON_DATA_I18N = sablon_data_i18n_kullanimi()


def _kullanim_birlesigi():
    """``USED`` + şablon ``data-i18n`` — yazım hatası taramasının kapsamı.

    ``USED`` olduğu gibi bırakılır: ona bağlı bekçilerin (ölü çeviri,
    şablon taramasının darlığı) ölçütleri DEĞİŞMEZ.
    """
    birlesik = {k: set(v) for k, v in USED.items()}
    for anahtar, kaynaklar in SABLON_DATA_I18N.items():
        birlesik.setdefault(anahtar, set()).update(kaynaklar)
    return birlesik


#: Yazım hatası korumasının kapsamı: JS çağrıları + şablon ``data-i18n``.
KULLANIM = _kullanim_birlesigi()


# ---------------------------------------------------------------------------
# 1. Sözdizimi
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
@pytest.mark.parametrize('path', SYNTAX_FILES, ids=lambda p: p.name)
def test_js_syntax_ok(path):
    result = subprocess.run([shutil.which('node'), '--check', str(path)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, '%s sözdizimi hatası:\n%s' % (path.name,
                                                                 result.stderr)


# ---------------------------------------------------------------------------
# 1a. Kapsamın kendisi — türetme daralmasın (ÖH FAZ D / D4)
# ---------------------------------------------------------------------------
def test_kapsam_turetilmis_ve_daralmadi():
    """`ALL_FILES` diskteki JS kümesinden türetilmiş olmalı, elle değil."""
    ust_duzey = {p.name for p in STATIC_JS.glob('*.js')}
    paneller = {p.name for p in PANELS_DIR.glob('*.js')}
    assert ust_duzey and paneller, 'JS dizinleri boş — yol mu değişti?'

    taranan = {p.name for p in ALL_FILES}
    sozluk = {p.name for p in SOZLUK_KAYNAKLARI}
    beklenen = (ust_duzey - sozluk) | paneller
    assert taranan == beklenen, (
        'ALL_FILES artık JS dizinlerini yansıtmıyor.\n'
        '  taranan ama diskte yok  : %s\n'
        '  diskte var ama taranmıyor: %s'
        % (sorted(taranan - beklenen), sorted(beklenen - taranan)))

    eksik = sorted(set(TARIHSEL_MODULE_FILES) - taranan)
    assert not eksik, (
        'Türetme elle liste döneminin kapsamını DARALTTI — düşen dosya: %s'
        % eksik)

    # P13B4-07'nin ölçülmüş kurbanı: bir panel, ama panels/ altında değil.
    assert 'blowdown_panel.js' in taranan, (
        'blowdown_panel.js yine kapsam dışı — elle liste ile glob arasındaki '
        'boşluk geri geldi (P13B4-07).')

    # Sözdizimi denetimi hiçbir JS dosyasını dışarıda bırakmaz.
    assert {p.name for p in SYNTAX_FILES} == ust_duzey | paneller, (
        'node --check kapsamı JS ağacını yansıtmıyor: %s'
        % sorted((ust_duzey | paneller) ^ {p.name for p in SYNTAX_FILES}))


def test_olu_ceviri_bekcisi_vakumlanmadi():
    """Sözlük KAYNAKLARI kullanım taramasına giremez.

    i18n_common.js'in kendi anahtar literalleri (`'common.axis.timeS2':`)
    FIELD_RE'ye uyar. Sözlük taransaydı her anahtar kendi kendini
    "kullanılıyor" ilan eder ve :func:`test_every_dictionary_key_is_used`
    sessizce vakumlanırdı — kapsam genişletmenin en olası yan hasarı budur.
    """
    kirletenler = sorted(p.name for p in ALL_FILES if _sozluk_kaynagi(p))
    assert not kirletenler, (
        'Sözlük kaynağı kullanım taramasına girmiş: %s — ölü çeviri bekçisi '
        'kendi kendini doğrulamaya başlar.' % kirletenler)
    assert SOZLUK_KAYNAKLARI, 'Sözlük kaynağı hiç bulunamadı — ölçüt bozuk mu?'
    # Ölçütün AŞIRI dışlamadığı da denetlenir: dışlanan her dosya gerçekten
    # bir sözlük gövdesi taşımalı. Aşırı dışlama = sessiz kör nokta.
    sozluksuz = sorted(p.name for p in SOZLUK_KAYNAKLARI
                       if not re.search(r'\bDICT\s*=\s*\{',
                                        read(p)))
    assert not sozluksuz, (
        'Kapsam dışı bırakılan dosya sözlük gövdesi taşımıyor: %s — ölçüt '
        '(I18N.register çağrısı) düz bir tüketiciyi dışarıda bıraktı.'
        % sozluksuz)
    # Ölçütün gerçekten yük taşıdığının kanıtı: sözlük anahtarlarının bir
    # bölümü FIELD_RE'ye uyuyor, yani taransaydı kendi kendini onaylardı.
    kendini_onaylar = [k for k in EN if FIELD_RE.search("'%s'" % k)]
    assert kendini_onaylar, (
        'Sözlük anahtarlarının hiçbiri FIELD_RE ile eşleşmiyor — muafiyetin '
        'gerekçesi ölçümle tutmuyor, gerekçe güncellenmeli.')


def test_dictionary_exists_and_is_registered():
    assert DICT_JS.exists(), 'hrma/static/js/i18n_common.js yok'
    source = read(DICT_JS)
    assert "I18N.register(DICT, 'i18n_common.js')" in source, \
        'i18n_common.js register() çağırmıyor — sözlük hiç yüklenmez'
    assert '__I18N_PENDING' in source, \
        'i18n_common.js yükleme sırası koruması (__I18N_PENDING) içermiyor'
    assert len(EN) > 500, 'EN sözlüğü beklenenden küçük: %d anahtar' % len(EN)


def test_en_tr_key_sets_match_and_values_non_empty():
    assert set(EN) == set(TR), (
        'EN/TR anahtar kümeleri farklı: yalnız EN %s, yalnız TR %s'
        % (sorted(set(EN) - set(TR))[:10], sorted(set(TR) - set(EN))[:10]))
    empty = sorted(k for k in EN if not EN[k].strip() or not TR[k].strip())
    assert not empty, 'Boş çeviri değeri: %s' % empty


def test_english_block_has_no_turkish_letters():
    """EN bloğuna yanlışlıkla Türkçe metin sızmasın (blokların karışması)."""
    turkish = re.compile(r'[çğıİöşüÇĞÖŞÜ]')

    def _metin(k, v):
        # v3.0.1 (NK-51): proj.nameRule izin verilen Türkçe harfleri SAYAR;
        # o liste metin değil karakter kümesidir. Yalnız tam liste çıkarılır,
        # değerin geri kalanı yine denetlenir.
        return v.replace('ç ğ ı İ ö ş ü', '') if k == 'proj.nameRule' else v
    slips = sorted(k for k, v in EN.items()
                   if turkish.search(_metin(k, v)) and 'Türkçe' not in v)
    assert not slips, 'EN bloğunda Türkçe karakterli değerler: %s' % slips[:10]


# ---------------------------------------------------------------------------
# 2. İki yönlü tutarlılık
# ---------------------------------------------------------------------------
#: Ana sayfa sözlüğü (i18n.js çekirdeği) bu dosyanın kapsamı dışında
CORE_PREFIXES = ('lang.', 'page.', 'hero.', 'cap.', 'section.', 'card.',
                 'btn.', 'link.', 'footer.', 'nav.')


def _sozlukte_olmayanlar():
    """Kullanılan ama sözlükte karşılığı olmayan anahtarlar.

    Kapsam ÖH D33-3 / OH-D33-32'de ``KULLANIM``a genişledi: JS çağrıları
    + şablonların ``data-i18n`` nitelikleri.
    """
    return sorted(k for k in KULLANIM
                  if k not in EN and k not in DIGER_PARCALAR
                  and not k.startswith(CORE_PREFIXES))


def _ayrintili(anahtarlar):
    return '\n'.join('  %s  (%s)' % (k, ', '.join(sorted(KULLANIM[k])))
                     for k in anahtarlar[:25])


#: ÖH D33-3 / OH-D33-32 — KAPSAM GENİŞLEMESİNİN ORTAYA ÇIKARDIĞI BORÇ.
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33-3/bekci-cevirisi/a1/once.json`` K3,
#: taban ``fa7c4e1d`` ve ortak taban ağacı — iki ağaçta da AYNI beş ad):
#: ``formulas.html`` beş düğümü sözlükten çizmek istiyor, beşinin de
#: karşılığı hiçbir sözlükte yok, yani TR kullanıcı bu beş "model farkı"
#: notunu İNGİLİZCE okuyor. ``fx.s8_2.model_note`` ile BİREBİR aynı
#: sınıf; onu fix-37c ödemişti.
#:
#: Borç bu kulvarda ÖDENEMEZ: ödeme ``hrma/static/js/i18n_formulas.js``e
#: EN+TR girdisi yazmaktır, o dosya ``arayuz-i18n`` kulvarının sahasıdır
#: (ve bu dalgada o kulvar tarafından fiilen düzenleniyor — ölçüldü,
#: ``git diff --name-only fa7c4e1d HEAD``). Borç ADIYLA devredildi.
#:
#: İM DEĞİL ENVANTER: liste ``test_sablon_ceviri_borcu_tam_kume`` ile TAM
#: KÜME olarak kilitlenir — yeni bir sözlüksüz anahtar da, ödenmiş bir
#: borcun listede unutulması da KIRMIZI verir. Sessiz geçiş yok.
SABLON_CEVIRI_BORCU = (
    'fx.toc.modelGapNotice',
)


#: ÖH D34 · kulvar ``kabuk-erisilebilirlik`` — SÖZLÜĞE DEVREDİLEN ANAHTARLAR.
#:
#: Dalga kuralı: ``hrma/static/js/i18n_*.js`` YALNIZ ``metin-i18n``
#: kulvarınındır. Başka kulvar yeni bir kullanıcı metnine ihtiyaç duyunca
#: çağrısını ``T(key, default)`` / ``TF(key, params, default)`` ile kurar,
#: İngilizce yedeği bırakır ve anahtarı ADIYLA devreder. Yani bu anahtarlar
#: ürün hatası değil, İLAN EDİLMİŞ BORÇTUR: TR kullanıcı şimdilik İngilizce
#: yedeği okur.
#:
#: Kilit ``SABLON_CEVIRI_BORCU`` ile aynı ölçüttedir ve İKİ YANLIDIR:
#: listede olmayan yeni bir sözlüksüz JS anahtarı çıkarsa da, listedeki bir
#: ad sözlüğe girdiği hâlde listede kaldığı için de KIRMIZI verir. Borç ne
#: sessizce büyür ne sessizce ödenir.
#:
#: Kaynak: OH-GT-13 (sekme şeridi etiketi), OH-GT-14 (güvertenin uç ret
#: metinleri), OH-GT-18 (sürüm durumu). İngilizce karşılıkları çağrı
#: yerindeki yedeklerdir.
#:
#: BORÇ ÖDENDİ — ÖH D37 A1a · dil-sozluk (DV-D34KEYS). 15 adın hepsi
#: ``i18n_common.js`` EN+TR bloklarına girdi (EN metni çağrı yerindeki
#: yedekle AYNI); bu bekçi tam da bunu istedi: "listeden DÜŞMELİDİR —
#: kırmızı, güncellemenin kendisidir". Küme boş kalır, kilit ölçütü aynen
#: sürer (yeni bir sözlüksüz JS anahtarı çıkarsa
#: ``test_every_used_key_exists_in_dictionary`` kırmızı verir). Ödemenin
#: davranış bekçisi: ``tests/test_d37_dil_a1.py`` (TR kipte güverte uç
#: reddi Türkçe, 15 anahtar kodda kullanılıyor).
D34_DEVREDILEN_ANAHTARLAR = ()


def test_d34_devredilen_anahtarlar_TAM_KUME():
    """Devredilen borç TAM KÜME olarak kilitli (im değil, envanter)."""
    sozluksuz = set(_sozlukte_olmayanlar())
    taban = set(D34_DEVREDILEN_ANAHTARLAR)
    odenen = sorted(taban - sozluksuz)
    assert not odenen, (
        'D34_DEVREDILEN_ANAHTARLAR bayatladı: %s. Bu adlar artık sözlükte '
        '(metin-i18n borcu ödedi) ya da çağrıdan kalktı; her iki hâlde de '
        'listeden DÜŞMELİDİR — kırmızı, güncellemenin kendisidir.' % odenen)


def _sablon_kapsam_borcu():
    """Yalnız KAPSAM GENİŞLEMESİNİN gördüğü sözlüksüz anahtarlar."""
    return sorted(k for k in _sozlukte_olmayanlar()
                  if k in SABLON_DATA_I18N and k not in USED)


def test_every_used_key_exists_in_dictionary():
    """Kodda çağrılan anahtarın sözlükte karşılığı olmalı (yazım hatası).

    D4 kapsam genişlemesinin açtığı borç iki ADLANDIRILMIŞ aileyle
    sınırlıdır (K3: `shell.*` + `blowdown.*`) ve ayrı bir bekçide
    xfail(strict) ile imlidir. Onun dışında kalan her sözlüksüz anahtar —
    yeni eklenen bir dosyadaki yazım hatası dahil — burada KIRMIZI verir.
    """
    missing = [k for k in _sozlukte_olmayanlar()
               if not k.startswith(CEVIRI_BORCU_AILELERI)
               and k not in SABLON_CEVIRI_BORCU
               and k not in D34_DEVREDILEN_ANAHTARLAR]
    assert not missing, ('Sözlükte olmayan anahtarlar (%d):\n%s'
                         % (len(missing), _ayrintili(missing)))


def test_sablon_ceviri_borcu_tam_kume():
    """OH-D33-32 borcu TAM KÜME olarak kilitlidir (im değil, envanter).

    Ne büyüme ne de sessiz ödeme olabilir:

    * listede OLMAYAN bir sözlüksüz şablon anahtarı çıkarsa -> KIRMIZI
      (kapsam boşluğunun geri gelmesi);
    * listedeki bir ad sözlüğe girdiyse -> KIRMIZI, çünkü artık borç
      değildir ve listeden DÜŞMESİ gerekir. Kırmızı, güncellemenin
      kendisidir (``test_envanter_tek_dosyaya_cokmedi`` ile aynı ölçüt).
    """
    bugun = set(_sablon_kapsam_borcu())
    taban = set(SABLON_CEVIRI_BORCU)
    yeni = sorted(bugun - taban)
    odenen = sorted(taban - bugun)
    assert not yeni, (
        'Şablonda kullanılıp hiçbir sözlükte olmayan YENİ anahtar (%d): %s\n'
        'TR kullanıcı bu düğümleri İngilizce okur. Sözlüğe EN+TR girdisi '
        'ekleyin (ürün işi) ya da anahtarı düzeltin.'
        % (len(yeni), _ayrintili(yeni)))
    assert not odenen, (
        'SABLON_CEVIRI_BORCU listesi bayatladı: %s. İki sebepten biri — '
        'ya borç ÖDENDİ (anahtar sözlüğe girdi: %s) ya da düğüm '
        'ŞABLONDAN KALKTI (artık data-i18n ile çağrılmıyor: %s). Hangisi '
        'olursa olsun ad listeden düşmelidir; ikisi de sessizce geçemez.'
        % (odenen,
           sorted(k for k in odenen
                  if k in EN or k in DIGER_PARCALAR),
           sorted(k for k in odenen if k not in SABLON_DATA_I18N)))


def test_sablon_data_i18n_kapsami_canli():
    """Kapsam gerçekten genişledi mi? (OH-D33-32 ölçümü)

    ÖLÇÜLDÜ (``a1/once.json`` K3): sekiz şablon 1.915 ayrık ``data-i18n``
    anahtarı çağırıyor; bunların hiçbiri eski kapsamda değildi. Taban
    1.500'dür — türetme daralırsa (ör. dizin yolu değişirse) bu bekçi
    kırmızı verir, sessizce boş küme taramaz.
    """
    assert len(SABLON_DATA_I18N) > 1500, len(SABLON_DATA_I18N)
    # fix-37c'nin ödediği borç: JS'te HİÇ geçmez, yalnız şablonda yaşar.
    # Eski kapsam bu anahtarı göremiyordu; yeni kapsam görüyor.
    assert 'fx.s8_2.model_note' in SABLON_DATA_I18N
    assert 'fx.s8_2.model_note' not in USED
    assert 'fx.s8_2.model_note' in KULLANIM
    # Kapsam SÖZLÜĞÜ değil KULLANIMI büyütür: ölü çeviri bekçisinin
    # ölçütü (USED + SABLON_KULLANIMI) DEĞİŞMEDİ.
    assert set(USED) <= set(KULLANIM)
    assert set(SABLON_DATA_I18N) <= set(KULLANIM)


# BORÇ İMİ KALDIRILDI — ÖH D27 / arayuz a2 (P12aB1-02).
# Eski im: "52 shell.* + 18 blowdown.* çevrilmemiş; çeviri eklemek
# ÜRÜN işidir ... xfail onarım dalgasında kalkar." Onarım dalgası
# BUDUR: 18 `blowdown.*` anahtarı (+ 6 künye etiketi) sözlüğe girdi
# ve bu düğüm XPASS(strict) ile KIRMIZI verdi. Ölçüm: sözlüksüz
# anahtar sayısı 0 (shell.* 0, blowdown.* 0). Bekçi artık CANLIdır.
def test_ceviri_borcu_aileleri_sozlukte():
    """`shell.*` ve `blowdown.*` aileleri de sözlükte olmalı (bugün değil)."""
    missing = [k for k in _sozlukte_olmayanlar()
               if k.startswith(CEVIRI_BORCU_AILELERI)]
    # Borcun KAYNAĞI da ölçülür: bu aileler yalnız D4 ile kapsama giren
    # dosyalardan geliyor olmalı. Eski kapsamdan gelen bir üye çıkarsa borç
    # imi yanlış yere konmuş demektir.
    yanlis_yerde = sorted(k for k in missing
                          if not (KULLANIM[k] <= YENI_KAPSAM))
    assert not yanlis_yerde, (
        'Borç ailesi eski kapsamdan da geliyor — bu bir borç imi değil, '
        'gerçek regresyon: %s' % _ayrintili(yanlis_yerde))
    assert not missing, ('Çeviri borcu aileleri (%d):\n%s'
                         % (len(missing), _ayrintili(missing)))


def test_every_dictionary_key_is_used():
    """Ölü çeviri koruması: sözlükteki her anahtar kodda geçmeli.

    Tek istisna DEVREDILEN_OLU_ANAHTARLAR'dır: adı, halefi ve gerekçesi
    yazılı, silinmesi başka bir kulvara devredilmiş girdiler. İstisna bedava
    değil — halefin gerçekten tanımlı VE kullanımda olduğu ayrıca ölçülür
    (bkz. test_devredilen_olu_anahtarin_halefi_yasiyor).

    "Kod" üç kaynaktır: ``hrma/static/js`` (USED), Python motorlarının
    ürettiği kodlar (``python_dispatched_keys``) ve sayfa şablonları
    (``sablon_kullanimi``, ÖH D24 / fix-22 — gerekçesi orada yazılı).
    """
    unused = sorted(k for k in EN
                    if k not in USED and k not in SABLON_KULLANIMI
                    and k not in DEVREDILEN_OLU_ANAHTARLAR)
    assert not unused, ('Kodda kullanılmayan sözlük anahtarları (%d): %s'
                        % (len(unused), unused[:25]))


def test_sablon_taramasi_dar_ve_olculen_anahtarlari_goruyor():
    """Şablon kaynağı ölü-çeviri bekçisini VAKUMLAMAZ (ÖH D24 / fix-22).

    İki ayak birlikte ölçülür:

    1. Kör noktanın kendisi — D23'ün şablonda ürettiği üç ``panelwarn.*``
       kodu JS taramasında YOK, şablon taramasında VAR. Ayak düşerse
       (ör. kodlar JS'e taşınırsa) bu bekçi kırmızı verir ve şablon
       taramasının hâlâ gerekli olup olmadığı yeniden ölçülür.
    2. Genişliğin sınırı — şablon taraması sözlüğün tamamını
       "kullanılıyor" ilan etmiyor; ölü çeviri koruması ayakta kalıyor.
    """
    olculen = ('panelwarn.liquid.valve_regime_not_verified',
               'panelwarn.liquid.roughness_provenance_undeclared',
               'panelwarn.solid.nozzle_thermal_not_evaluated')
    for anahtar in olculen:
        assert anahtar in EN, 'ölçülen anahtar sözlükten düşmüş: %s' % anahtar
        assert anahtar in SABLON_KULLANIMI, (
            'şablon taraması ölçülen anahtarı görmüyor: %s' % anahtar)
        assert anahtar not in USED, (
            '%s artık JS tarafında da geçiyor — şablon taramasının gerekçesi '
            'yeniden ölçülmeli' % anahtar)
    kapsanan = sum(1 for k in EN if k in SABLON_KULLANIMI)
    assert kapsanan * 2 < len(EN), (
        'şablon taraması sözlüğün %d/%d anahtarını "kullanılıyor" sayıyor — '
        'ölü çeviri bekçisi vakumlanmış olabilir' % (kapsanan, len(EN)))


def test_devredilen_olu_anahtarin_halefi_yasiyor():
    """Devredilen her ölü anahtarın halefi tanımlı ve kullanımda olmalı."""
    for olu, halef in sorted(DEVREDILEN_OLU_ANAHTARLAR.items()):
        assert olu not in USED, (
            '%s artık kullanımda — devir kaydı bayat, listeden çıkarın' % olu)
        assert halef in EN or halef in DIGER_PARCALAR, (
            '%s halefi %s hiçbir sözlük parçasında tanımlı değil' % (olu, halef))
        assert halef in USED, ('%s halefi %s kodda kullanılmıyor'
                               % (olu, halef))


# ---------------------------------------------------------------------------
# OH-D19-29 (A) — i18n_shell.js ölü-anahtar süpürmesi (kapsam: TEK AİLE)
# ---------------------------------------------------------------------------
#: Süpürmenin kapsadığı ad alanı. Kapsam bir AİLEYLE sınırlıdır ve bu bir
#: gevşetme değil, ÖLÇÜLMÜŞ bir sınırdır (hüküm-21b, Opus uç arayuz-i18n-01):
#: ``i18n_shell.js``in 110 anahtarının 40'ı bu taramaya "kullanılmıyor"
#: görünür, çünkü tüketicileri ``hrma/static/js`` DIŞINDADIR (Electron
#: kabuğu: ``shell.bug.*``, ``update.*``, ``proj.*``, ``link.*``). Onları
#: süpürmek 40 sahte kırmızı üretirdi. ``stepimp`` ailesinin tüketicisi ise
#: taramanın İÇİNDEdir (``step_import_ui.js``), dolayısıyla fail-closed
#: süpürülebilir. Kapsamın genişletilmesi Electron tarafını da tarayan bir
#: kapsam türetmesi gerektirir — ayrı kalem.
SHELL_SUPURULEN_AILE = 'stepimp.'
SHELL_JS = STATIC_JS / 'i18n_shell.js'


def _shell_anahtarlari():
    """``i18n_shell.js``te TANIMLI anahtarlar (sözlük gövdesinden)."""
    metin = SHELL_JS.read_text(encoding='utf-8')
    return {k.replace("\\'", "'") for k in re.findall(
        r"^\s*'((?:[^'\\]|\\.)*)':\s*'", metin, re.M)}


def test_shell_supurulen_ailede_olu_anahtar_yok():
    """i18n_shell.js için ölü-anahtar süpürmesi — ÖH D33 / OH-D19-29 (A).

    ÖLÇÜLDÜ (a1/once.json OH-D19-29, taban 56f88e70): ölü-çeviri bekçisi
    (``test_every_dictionary_key_is_used``) YALNIZ ``EN`` üzerinde, yani
    ``i18n_common.js`` üzerinde dönüyordu. ``i18n_shell.js``te tanımlı
    **110 anahtarın hiçbiri** hiçbir ölü-anahtar taramasına girmiyordu:
    o dosyaya yazılan bir anahtar hiç kullanılmasa da depo yeşil kalırdı.
    ``register()`` parçaları aynı tabloya birleştirdiği için bu, sözlüğün
    yarısının denetimsiz olması demekti.

    Süpürme bu ailede FAIL-CLOSED'dır: ailede tanımlı her anahtarın kodda
    (ya da şablonda) geçtiği istenir; geçmeyen kırmızı verir.
    """
    aile = sorted(k for k in _shell_anahtarlari()
                  if k.startswith(SHELL_SUPURULEN_AILE))
    assert aile, (
        '%s ailesi i18n_shell.js\'te tanımlı değil — süpürme vakumlanmış, '
        'kapsam yeniden ölçülmeli' % SHELL_SUPURULEN_AILE)
    olu = [k for k in aile if k not in USED and k not in SABLON_KULLANIMI]
    assert not olu, (
        'i18n_shell.js %s ailesinde ÖLÜ anahtar (%d/%d): %s'
        % (SHELL_SUPURULEN_AILE, len(olu), len(aile), olu))


def test_shell_supurmesi_kapsamini_beyan_ediyor():
    """Süpürmenin sınırı ÖLÇÜLÜR ve saklanmaz (kapsam beyanı).

    İki ayak:

    1. **Sınırın gerçekliği** — kapsam dışı bırakılan ailelerde bu taramaya
       görünmeyen anahtarlar GERÇEKTEN vardır; yani daraltma keyfî değil,
       ölçülmüş bir kısıttır. Sayı sıfıra düşerse (Electron tarafı da
       taranır hâle gelirse) bu bekçi kırmızı verir ve kapsamın
       genişletilmesi gerektiğini söyler.
    2. **Daraltmanın sınırı** — süpürülen aile sözlüğün TAMAMI değildir,
       ama boş da değildir; süpürme gerçek bir iş yapar.
    """
    shell = _shell_anahtarlari()
    aile = {k for k in shell if k.startswith(SHELL_SUPURULEN_AILE)}
    kapsam_disi_gorunmez = sorted(
        k for k in shell - aile
        if k not in USED and k not in SABLON_KULLANIMI)
    assert kapsam_disi_gorunmez, (
        'i18n_shell.js\'in kapsam dışı ailelerinde artık taramaya görünmeyen '
        'anahtar YOK — Electron tarafı da taranır hâle gelmiş olabilir; '
        'süpürme kapsamı tek aileden çıkarılıp tüm dosyaya genişletilmeli '
        '(OH-D19-29 (A) kapsam kaydı)')
    assert aile and len(aile) < len(shell), (
        'süpürülen aile sözlüğün tamamı ya da boş: kapsam kaydı bayat '
        '(%d/%d)' % (len(aile), len(shell)))


# ---------------------------------------------------------------------------
# 3. Dil değişiminde yeniden basma
# ---------------------------------------------------------------------------
def test_dock_rerenders_panels_on_language_change():
    """Güverte, saklanan yanıtla panelleri yeniden çizen bir onChange kaydeder."""
    src = read(STATIC_JS / 'analysis_dock.js')
    assert 'I18N.onChange' in src, 'analysis_dock.js dil değişimini dinlemiyor'
    assert 'lastData' in src, \
        'analysis_dock.js son yanıtı saklamıyor — dil değişince panel boşalır'
    assert 'function rerenderAll' in src, \
        'analysis_dock.js rerenderAll() kaybolmuş (dil değişiminde yeniden çizim)'


@pytest.mark.parametrize('name', [
    'app.js', 'injector_panel.js', 'sixdof_panel.js', 'transient_panel.js',
])
def test_self_mounted_modules_listen_for_language_change(name):
    """Kendi DOM'unu kuran modüller dil değişimini dinlemeli."""
    src = read(STATIC_JS / name)
    assert 'I18N.onChange' in src, \
        '%s dil değişiminde kendini yeniden basmıyor' % name


def test_feed_panel_rerenders_tabs_on_language_change():
    src = read(PANELS_DIR / 'feed_panel.js')
    assert 'I18N.onChange' in src and 'rerenderTabs' in src, \
        'feed_panel.js kendi sekmelerini dil değişiminde yenilemiyor'


# ---------------------------------------------------------------------------
# 4. Güverte sözleşmesi: başlık ve alan etiketleri anahtarlı
# ---------------------------------------------------------------------------
def test_dock_supports_label_keys():
    src = read(STATIC_JS / 'analysis_dock.js')
    assert 'titleKey' in src, 'analysis_dock.js panel başlığı anahtarını okumuyor'
    assert 'i18nAttr(' in src, \
        'analysis_dock.js etiketlere data-i18n basmıyor — dil değişince form İngilizce kalır'


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_panel_registers_title_key(path):
    src = strip_comments(read(path))
    if 'AnalysisDock.register(' not in src:
        pytest.skip('%s güverteye panel kaydetmiyor' % path.name)
    assert 'titleKey:' in src, \
        '%s panel başlığı için titleKey vermiyor (başlık çevrilmez)' % path.name
    key = re.search(r"titleKey:\s*'([\w.]+)'", src).group(1)
    assert key in EN, '%s titleKey sözlükte yok: %s' % (path.name, key)


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_panel_field_labels_have_keys(path):
    """`fields: [[id, 'Label', def, step]]` biçiminde anahtarsız alan kalmasın."""
    src = strip_comments(read(path))
    match = re.search(r'fields:\s*\[', src)
    if not match:
        pytest.skip('%s alan listesi tanımlamıyor' % path.name)
    depth = 0
    start = match.end() - 1
    for idx in range(start, len(src)):
        if src[idx] == '[':
            depth += 1
        elif src[idx] == ']':
            depth -= 1
            if depth == 0:
                body = src[start + 1:idx]
                break
    # Yalnız ÜST düzey alan satırları: ['id', 'Label', varsayılan, adım, 'anahtar']
    # (seçenek listeleri iç içe dizidir, ayrı ayrı denetlenmez).
    rows = []
    depth = 0
    row_start = None
    for idx, ch in enumerate(body):
        if ch == '[':
            depth += 1
            if depth == 1:
                row_start = idx
        elif ch == ']':
            depth -= 1
            if depth == 0 and row_start is not None:
                rows.append(body[row_start:idx + 1])
                row_start = None
    rows = [r for r in rows if re.match(r"\[\s*'[\w]+'\s*,\s*'", r)]
    bad = [r for r in rows if not re.search(r",\s*'[\w]+\.[\w.]+'\s*\]\s*$", r, re.S)]
    detail = '\n'.join('  ' + ' '.join(r.split())[:90] for r in bad[:10])
    assert not bad, ('%s içinde çeviri anahtarı olmayan alan etiketi (%d):\n%s'
                     % (path.name, len(bad), detail))


@pytest.mark.parametrize('cat', DOCK_CATEGORIES)
def test_dock_category_labels_translated(cat):
    key = 'dock.cat.' + cat
    assert key in EN, 'Kategori sekmesi çevirisi yok: %s' % key
    assert TR[key] != EN[key] or not re.search(r'[A-Za-z]{3,}', EN[key]), \
        '%s sekmesi Türkçeye çevrilmemiş' % cat


# ---------------------------------------------------------------------------
# 5. Kalıntı avı — düz metin geçen ortak UI çağrıları
# ---------------------------------------------------------------------------
LITERAL_CALLS = (
    # (çağrı, açıklama) — ilk argümanı düz tırnaklı metin olan kullanım
    (re.compile(r"U\.sectionTitle\(\s*'"), 'U.sectionTitle'),
    (re.compile(r"U\.listBlock\(\s*'"), 'U.listBlock'),
    (re.compile(r"U\.statCard\(\s*'(?![A-Za-z_]*'\s*\))"), 'U.statCard'),
)


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_no_hardcoded_section_titles(path):
    """Bölüm başlığı / uyarı kutusu başlığı doğrudan metinle çağrılmamalı."""
    src = strip_comments(read(path))
    hits = []
    for regex, label in LITERAL_CALLS[:2]:
        for match in regex.finditer(src):
            line = src.count('\n', 0, match.start()) + 1
            hits.append('%s:%d %s(...)' % (path.name, line, label))
    assert not hits, ('Çeviriden geçmeyen başlık çağrıları:\n  '
                      + '\n  '.join(hits))


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_status_messages_go_through_translation(path):
    """`status.textContent = 'metin'` gibi düz durum mesajı kalmamalı."""
    src = strip_comments(read(path))
    pattern = re.compile(r"(?:status|note|plotEl|el)\.textContent\s*=\s*'"
                         r"(?![A-Z_]{0,3}')([^']{4,})'")
    hits = []
    for match in pattern.finditer(src):
        line = src.count('\n', 0, match.start()) + 1
        hits.append('%s:%d  %r' % (path.name, line, match.group(1)[:60]))
    assert not hits, ('Çevrilmemiş durum mesajı:\n  ' + '\n  '.join(hits))


def test_no_emoji_in_dictionary():
    """Berke kuralı: arayüz metinlerinde emoji yok."""
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    found = [k for k in EN if emoji.search(EN[k]) or emoji.search(TR[k])]
    assert not found, 'Sözlükte emoji: %s' % found[:10]


def test_placeholders_match_between_languages():
    """{yer_tutucu} kümesi EN ve TR'de aynı olmalı (eksik parametre = bozuk metin)."""
    ph = re.compile(r'\{(\w+)\}')
    bad = []
    for key in EN:
        if set(ph.findall(EN[key])) != set(ph.findall(TR[key])):
            bad.append('%s: EN %s vs TR %s' % (key, sorted(set(ph.findall(EN[key]))),
                                               sorted(set(ph.findall(TR[key])))))
    assert not bad, 'Yer tutucu uyuşmazlığı:\n  ' + '\n  '.join(bad[:15])


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
