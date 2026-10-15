# -*- coding: utf-8 -*-
"""Parça-kopya bekçisi — sözlük girdisi, kodun tam fallback'inin ÖN EKİ olamaz.

NEDEN (2.6.27 yirminci parti, 15 Ağustos 2026 — ölçüldü):
fea_panel.js'teki uzun İngilizce fallback'ler kaynakta çok parçalı dize
birleştirmesiyle yazılır::

    T('fea.busy', 'Running — the solver refines the mesh until the '
        + 'peak stress stops changing; ...')

Anahtarlar sözlüğe taşınırken birleştirmenin YALNIZ İLK dizesi kopyalanmış;
sözlük girdisi fallback'i ezdiği için üründe 10 ayrı metin cümle ortasında
kesik basılıyordu ('fea.intro', 'fea.busy', 'fea.gaussNote', ... — tamamı bu
dosyanın taramasıyla bulundu ve onarıldı). Türkçe girdiler elle yazıldığı
için tamdı; kusur yalnız EN tarafındaydı ve hiçbir bekçi görmüyordu: ölü
çeviri bekçisi anahtarın VARLIĞINA bakar, içeriğine bakmaz.

KURAL: kod içinde T('anahtar', '<tam fallback>') olarak yaşayan her anahtar
için, EN sözlük değeri fallback'in KESİN ÖN EKİ (daha kısa hâli) olamaz.
Farklı olması serbesttir (sözlük metni bilinçli sadeleştirilmiş olabilir);
yasak olan tek şey "kopyala derken yarıda kesilmiş" imzasıdır.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATIC_JS = REPO / 'hrma' / 'static' / 'js'

# ---------------------------------------------------------------------------
# Kapsam — ÖH FAZ B-4 / FAZ D kuyruğu (elle liste → türetilmiş)
# ---------------------------------------------------------------------------
# Bu dosyanın kendi yorumu "test_i18n_common.py MODULE_FILES ile aynı
# disiplin" diyordu; o disiplin FAZ D'de (D4) türetmeye geçti, burası elle
# kaldı. İki elle liste (kaynaklar + sözlükler) ölçüldüğünde kapsamın
# neredeyse tamamı dışarıda çıktı.
#
# ÖLÇÜM (2026-08-27, bu depo):
#   * Elle 5 kaynak → 862 anahtar. Fallback TAŞIYAN dosya sayısı ise 39;
#     türetilmiş kapsam 2.389 anahtar → **1.527 anahtar hiç denetlenmiyordu**
#     (app.js 203, cfd_panel.js 144, sixdof_panel.js 101, … bug_report.js 22).
#   * Elle 3 sözlük → depoda 8 sözlük dosyası var (hepsi ``I18N.register(``
#     çağırıyor ve ``en:``/``tr:`` bölümlü); 5'i hiç taranmıyordu.
#   * ``advanced.html`` elle listedeydi ama HASADA 0 anahtar veriyordu
#     (P15B3-12'nin "katkı vermeyen üye" bulgusu). SEBEBİ ölçüldü: üye sahte
#     DEĞİL, HASATÇI kördü — advanced.html çeviriyi ``T(...)`` ile değil
#     ``i18nText(key, fallback)`` ile çağırıyor (``advanced.html:2473``) ve
#     eski desen ``\bTF?\(`` bu adı görmüyordu. Çağrı adı kapsama alınınca
#     aynı dosya **159 anahtar** veriyor. Yani üye düşmez, ölçüt düzelir.
#   * Genişlemenin açtığı borç: YOK — 39 kaynak × 8 sözlükte parça-kopya
#     kusuru 0 (elle kapsamda da 0'dı).
#
# Ölçütler (mekanik, elle muafiyet yok):
#   kaynak  = fallback taşıyan (en az bir ``T``/``TF``/``i18nText`` çağrısı
#             ikinci argümanı dize olan) dosya; sözlük kaynakları hariç.
#   sözlük  = ``I18N.register(`` çağıran ve ``en:``/``tr:`` bölümü olan js.

#: Çeviri çağrısı adları — TEK TANIM. Yeni bir sarmalayıcı ad doğarsa
#: buraya eklenir; ``test_cagri_adlari_kaynakta_gercekten_var`` bu listenin
#: çürümesini engeller.
CAGRI_ADLARI = ('T', 'TF', 'i18nText')
_CAGRI_RE = re.compile(
    r"\b(?:%s)\(\s*['\"]([\w.\-]+)['\"]\s*," % '|'.join(CAGRI_ADLARI))

#: Kapsam adayları: üst düzey JS + panel JS + şablonlar.
_ADAYLAR = (sorted(STATIC_JS.glob('*.js'))
            + sorted((STATIC_JS / 'panels').glob('*.js'))
            + sorted((REPO / 'hrma' / 'templates').glob('*.html')))


def _sozluk_kaynagi(path):
    """Dosya çeviri anahtarı TANIMLIYOR mu? (test_i18n_common.py ölçütü)"""
    if path.suffix != '.js':
        return False
    s = path.read_text(encoding='utf-8')
    if 'I18N.register(' not in s:
        return False
    en_m = re.search(r'^\s*en:\s*\{', s, re.M)
    tr_m = re.search(r'^\s*tr:\s*\{', s, re.M)
    return bool(en_m and tr_m and en_m.start() < tr_m.start())


#: Anahtar TANIMLAYAN dosyalar — türetilmiş (ölçüldü: 8).
DICTS = [p for p in _ADAYLAR if _sozluk_kaynagi(p)]

#: Elle liste dönemlerinin kapsamı — TABAN (türetme daralırsa kırmızı).
TARIHSEL_FALLBACK_SOURCES = ('fea_panel.js', 'thermal_fea_panel.js',
                             'solid.html', 'advanced.html', 'liquid.html')
TARIHSEL_DICTS = ('i18n_common.js', 'i18n_pages.js', 'i18n_advanced.js')


def _string_literal(s, i):
    """s[i] tırnak: literalin (değer, sonraki_indeks) çifti."""
    q = s[i]
    out = []
    i += 1
    while i < len(s):
        c = s[i]
        if c == '\\':
            nxt = s[i + 1]
            out.append({'n': '\n', 't': '\t', "'": "'", '"': '"',
                        '\\': '\\'}.get(nxt, nxt))
            i += 2
            continue
        if c == q:
            return ''.join(out), i + 1
        out.append(c)
        i += 1
    raise AssertionError('kapanmayan dize: %d' % i)


def _concat_from(s, i):
    """i'deki dize literalinden başlayıp ' + ' zincirini birleştirir."""
    parts = []
    while True:
        while i < len(s) and s[i] in ' \t\n':
            i += 1
        if i >= len(s) or s[i] not in '\'"':
            break
        val, i = _string_literal(s, i)
        parts.append(val)
        j = i
        while j < len(s) and s[j] in ' \t\n':
            j += 1
        if j < len(s) and s[j] == '+':
            i = j + 1
            continue
        break
    return ''.join(parts), i


def _skip_arg(s, i):
    """Dize olmayan bir argümanı (nesne literali / tanımlayıcı) atlar."""
    if i < len(s) and s[i] == '{':
        depth = 0
        while i < len(s):
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
            elif s[i] in '\'"':
                _, i = _string_literal(s, i)
                continue
            i += 1
        return i
    while i < len(s) and re.match(r'[\w$.\[\]()]', s[i]):
        i += 1
    return i


def harvest_fallbacks(path):
    """``T``/``TF``/``i18nText`` çağrılarından anahtar→tam fallback.

    Aynı anahtar birden çok yerde geçerse en UZUN fallback esas alınır
    (kısa bağlam kopyaları uzun metni yanlışlamasın).

    ÖH Faz B-4: çağrı adları ``CAGRI_ADLARI``dan gelir. Eski desen yalnız
    ``T``/``TF`` arıyordu ve ``advanced.html``in 159 anahtarlık
    ``i18nText(...)`` gövdesini HİÇ görmüyordu — dosya listede olduğu hâlde
    hasada 0 katkı veriyordu (P15B3-12'nin "katkı vermeyen üye" ölçümünün
    kökü)."""
    s = path.read_text(encoding='utf-8')
    out = {}
    for m in _CAGRI_RE.finditer(s):
        key, i = m.group(1), m.end()
        for _ in range(3):          # en fazla 2 ara argüman
            while i < len(s) and s[i] in ' \t\n':
                i += 1
            if i >= len(s):
                break
            if s[i] in '\'"':
                val, _son = _concat_from(s, i)
                if key not in out or len(val) > len(out[key]):
                    out[key] = val
                break
            yeni = _skip_arg(s, i)
            if yeni == i:
                break
            i = yeni
            while i < len(s) and s[i] in ' \t\n':
                i += 1
            if i < len(s) and s[i] == ',':
                i += 1
            else:
                break
    return out


def _fallback_kaynaklari(adaylar=None):
    """Fallback TAŞIYAN, sözlük olmayan dosyalar (türetilmiş)."""
    return [p for p in (_ADAYLAR if adaylar is None else adaylar)
            if not _sozluk_kaynagi(p) and harvest_fallbacks(p)]


#: Fallback taşıyan kaynaklar — TÜRETİLMİŞ (ölçüldü: 39 dosya, 2.389
#: anahtar). Yeni panel/şablon kendiliğinden kapsama girer.
FALLBACK_SOURCES = _fallback_kaynaklari()


def dict_entries(path):
    """Sözlük dosyasının YALNIZ EN bölümündeki girdiler.

    TR bölümü bilinçli dışarıda: çeviri, fallback'in ön eki olabilir ve bu
    kusur değildir (ölçülen örnek: TR 'Kerosen', EN fallback 'Kerosene'nin
    ön ekidir — doğru Türkçe kelimedir). Kesik-kopya hastalığı yalnız EN
    girdisi fallback'ten kopyalanırken oluşur."""
    s = path.read_text(encoding='utf-8')
    en_m = re.search(r'^\s*en:\s*\{', s, re.M)
    tr_m = re.search(r'^\s*tr:\s*\{', s, re.M)
    assert en_m and tr_m and en_m.start() < tr_m.start(), (
        '%s: en:/tr: bölüm yapısı beklenen düzende değil' % path.name)
    bas, son = en_m.end(), tr_m.start()
    out = []
    for m in re.finditer(r"['\"]([\w.\-]+)['\"]\s*:\s*(?=['\"])", s):
        if not (bas <= m.start() < son):
            continue
        val, _ = _concat_from(s, m.end())
        line = s.count('\n', 0, m.start()) + 1
        out.append((m.group(1), val, line))
    return out


def test_kapsam_turetilmis_ve_daralmamis():
    """Kaynak ve sözlük kapsamı türetilir; elle liste dönemini KAPSAR.

    ÖH Faz B-4 (FAZ D kuyruğu). İki yönlü kilit: daralma (ölçüt çürümesi,
    çağrı adının değişmesi) kırmızı verir; genişleme serbesttir — yeni
    panel/şablon/sözlük kendiliğinden taranır.

    Ölçüldü (2026-08-27): kaynak 39 dosya / 2.389 anahtar (elle dönem 5
    dosya / 862), sözlük 8 dosya (elle dönem 3).
    """
    kaynak_adlari = {p.name for p in FALLBACK_SOURCES}
    assert set(TARIHSEL_FALLBACK_SOURCES) <= kaynak_adlari, (
        'türetilmiş kaynak kapsamı elle liste döneminden DAR: kaybolan %s '
        '— çağrı adı ölçütü (%s) çürümüş olabilir'
        % (sorted(set(TARIHSEL_FALLBACK_SOURCES) - kaynak_adlari),
           list(CAGRI_ADLARI)))
    sozluk_adlari = {p.name for p in DICTS}
    assert set(TARIHSEL_DICTS) <= sozluk_adlari, (
        'türetilmiş sözlük kapsamı elle liste döneminden DAR: kaybolan %s'
        % sorted(set(TARIHSEL_DICTS) - sozluk_adlari))
    # Ölçüt ayırt ediyor mu (vakumlanma karşıtı): sözlükler kaynak
    # kapsamının DIŞINDA, ve her aday kapsama girmiyor.
    assert not (kaynak_adlari & sozluk_adlari), (
        'bir dosya hem kaynak hem sözlük sayıldı: %s'
        % sorted(kaynak_adlari & sozluk_adlari))
    assert len(FALLBACK_SOURCES) < len(_ADAYLAR), (
        'her aday kaynak sayıldı — ölçüt ayırt etmiyor')
    # advanced.html'in katkısı ölçülür: elle liste döneminde 0 idi.
    adv = next((p for p in FALLBACK_SOURCES if p.name == 'advanced.html'),
               None)
    assert adv is not None and len(harvest_fallbacks(adv)) > 100, (
        'advanced.html hasadı yine küçük — i18nText çağrı adı kapsamdan '
        'düşmüş olabilir (2026-08-27 ölçümü: 159 anahtar)')


def test_cagri_adlari_kaynakta_gercekten_var():
    """Çağrı adı listesi çürümesin: her ad en az bir kaynakta kullanılmalı.

    ÖH Faz B-4. Ölü bir ad listede kalırsa zararsızdır; asıl tehlike
    tersidir (kullanılan bir ad listede yok), ama o ancak bu bekçinin
    tersi ölçülerek görülemez — bu yüzden burada listeyi CANLI tutuyoruz:
    bir ad artık hiçbir kaynakta geçmiyorsa ya yeniden adlandırılmıştır
    (yeni adı eklenmeli) ya da satır silinmelidir.
    """
    metinler = [p.read_text(encoding='utf-8') for p in FALLBACK_SOURCES]
    for ad in CAGRI_ADLARI:
        desen = re.compile(r"\b%s\(\s*['\"][\w.\-]+['\"]\s*," % re.escape(ad))
        assert any(desen.search(m) for m in metinler), (
            "çeviri çağrı adı %r hiçbir kaynakta geçmiyor — yeniden "
            "adlandırılmışsa yeni adı CAGRI_ADLARI'na eklenmeli" % ad)


def test_sozluk_girdisi_fallback_on_eki_degil():
    fallbacks = {}
    for p in FALLBACK_SOURCES:
        assert p.exists(), 'fallback kaynağı kayıp: %s' % p
        for k, v in harvest_fallbacks(p).items():
            if k not in fallbacks or len(v) > len(fallbacks[k]):
                fallbacks[k] = v
    assert len(fallbacks) > 100, (
        'fallback hasadı beklenenden küçük (%d) — tarayıcı desenleri '
        'kaynaklarla uyumsuz olabilir' % len(fallbacks))
    kusur = []
    for dpath in DICTS:
        for key, val, line in dict_entries(dpath):
            fb = fallbacks.get(key)
            if fb is None or val == fb:
                continue
            if fb.startswith(val) and len(val) < len(fb):
                kusur.append('%s:%d  %s\n    sözlük: %r\n    tam   : %r' %
                             (dpath.name, line, key, val[:60], fb[:60]))
    assert not kusur, (
        'Parça-kopya kusuru: sözlük girdisi, kodun tam fallback metninin '
        'kesik ön eki (%d girdi). Girdiyi tam metinle değiştirin:\n%s'
        % (len(kusur), '\n'.join(kusur[:10])))


def test_bekci_kendini_yakalar():
    """Tautoloji karşıtı kanıt: hasat mekanizması bilinen bir tam fallback'i
    gerçekten çıkarabiliyor ve ön-ek karşılaştırması gerçekten çalışıyor.

    (Onarılmış vakanın ta kendisi: fea.busy'nin fallback'i çok parçalıdır;
    ilk parçası sözlükte dursaydı bu bekçi kırmızıya düşerdi.)"""
    fb = harvest_fallbacks(STATIC_JS / 'fea_panel.js')
    assert 'fea.busy' in fb
    tam = fb['fea.busy']
    ilk_parca = 'Running — the solver refines the mesh until the '
    assert tam.startswith(ilk_parca) and len(tam) > len(ilk_parca), (
        'fea.busy fallback birleştirmesi artık farklı — bekçinin kanıt '
        'vakasını güncelleyin')
