# -*- coding: utf-8 -*-
"""ÖH D30 · arayuz-panel a1 — şablon satır içi betiklerinin ``app.js``i
gölgelemesi (OH-D29-02; ÇİFT: P12bB3-09, OH-D28-10, P12bS1-06).

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D30/arayuz-panel/a1/once.json``, taban
``ab7cf68b``):

* ``app.js`` 8 şablonun YALNIZ birinde (``advanced.html``) yükleniyor.
* O sayfanın satır içi betiği ``app.js``in **11** üst düzey işlevini aynı
  adla yeniden bildiriyordu; bildirim ``<script src=".../app.js">``
  etiketinden SONRA geldiği için hoisting satır içi sürümü kazandırıyordu.
  Yani ``app.js``teki 446 satır **hiç koşmuyordu**.
* Gölgelemenin ürün bedeli ölçüldü: ``assertParametricMatchesRequest``
  (ucun yankısını isteğe karşı denetleyen fail-closed kapı) tek çağrısını
  ölü ``app.js::calculateParametric`` içinde taşıyordu — depoda tek bir
  test referansı bile yoktu. Kapı sessizce ölmüştü.

D28 arayuz a3 dersi (kapı kaybı) bu yüzden sökümün ön koşuludur: hangi
sürümün kazandığı SAYFA SAYFA ölçülmeden hiçbir gövde silinmez.

Bu bekçiler onarımın üç ayağını da bağlar: (1) canlı gölge kalmadı,
(2) sökülen gövdeler geri gelmedi, (3) gölgelemenin öldürdüğü kapı canlı
akışa yeniden bağlandı.
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
TPL = KOK / 'hrma' / 'templates'

#: Onarımdan SONRAKİ gerçek: hiçbir şablon ``app.js``i gölgelemiyor.
#: (D27 dersi 11 — sayım mandalı değil KÜME ölçüsü.)
CANLI_GOLGE = frozenset()

#: D30 a1'de sökülen ölü gövdeler (11 gölgelenen + yalnız onlardan
#: çağrılan 2 yardımcı). Geri gelirlerse bekçi kırmızıdır.
SOKULEN = frozenset({
    'calculateParametric', 'downloadEngFile', 'exportSTL', 'generateCAD',
    'generateCompletePackage', 'reset3DView', 'rotate3DView',
    'showDesignConfig', 'showLoading', 'showMessage', 'switchConfigTab',
    'assertCadContent', 'autoFillDesignConfig',
})

_DEGER_SONU = re.compile(r'[\w$\)\]]\s*$')


def _siyir(kaynak):
    """Yorum/dize/şablon/regex içeriğini boşlukla değiştirir (uzunluk korunur)."""
    out = list(kaynak)
    n = len(kaynak)
    i = 0
    while i < n:
        c = kaynak[i]
        if c == '/' and kaynak[i + 1:i + 2] == '/':
            j = kaynak.find('\n', i)
            j = n if j < 0 else j
            out[i:j] = [' '] * (j - i)
            i = j
            continue
        if c == '/' and kaynak[i + 1:i + 2] == '*':
            j = kaynak.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if kaynak[k] != '\n':
                    out[k] = ' '
            i = j
            continue
        if c in '"\'':
            j = i + 1
            while j < n:
                if kaynak[j] == '\\':
                    j += 2
                    continue
                if kaynak[j] == c or kaynak[j] == '\n':
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if kaynak[k] != '\n':
                    out[k] = ' '
            i = min(j + 1, n)
            continue
        if c == '`':
            j, derin = i + 1, 0
            while j < n:
                if kaynak[j] == '\\':
                    j += 2
                    continue
                if kaynak[j] == '$' and kaynak[j + 1:j + 2] == '{':
                    derin += 1
                    j += 2
                    continue
                if kaynak[j] == '}' and derin > 0:
                    derin -= 1
                    j += 1
                    continue
                if kaynak[j] == '`' and derin == 0:
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if kaynak[k] != '\n':
                    out[k] = ' '
            i = min(j + 1, n)
            continue
        if c == '/':
            if _DEGER_SONU.search(''.join(out[max(0, i - 64):i])):
                i += 1
                continue
            j, sinif, kapandi = i + 1, False, False
            while j < n:
                ch = kaynak[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '\n':
                    break
                if ch == '[':
                    sinif = True
                elif ch == ']':
                    sinif = False
                elif ch == '/' and not sinif:
                    kapandi = True
                    break
                j += 1
            if kapandi:
                out[i + 1:j] = [' '] * (j - i - 1)
                i = j + 1
                continue
            i += 1
            continue
        i += 1
    return ''.join(out)


def _ustduzey(kaynak):
    """{ad: [(bas, bit)]} — süslü parantez DERİNLİĞİ 0'daki bildirimler.

    Girinti değil DERİNLİK ölçülür: girinti bir biçim ölçüsüdür, derin
    girintili üst düzey bildirimi kaçırır ve iç içe bildirimi yanlışlıkla
    üst düzey sayar (D29 ölçümü bu yüzden 11 yerine 6 buluyordu).
    """
    s = _siyir(kaynak)
    bulgu, derinlik, i, n = {}, 0, 0, len(s)
    while i < n:
        c = s[i]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
        elif derinlik == 0 and (s.startswith('function', i)
                                or s.startswith('async', i)):
            onc = s[i - 1] if i else ' '
            if not (onc.isalnum() or onc in '_$.'):
                m = re.match(
                    r'(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(',
                    s[i:i + 200])
                if m:
                    j = s.find('{', i)
                    if j >= 0:
                        d, k = 0, j
                        while k < n:
                            if s[k] == '{':
                                d += 1
                            elif s[k] == '}':
                                d -= 1
                                if d == 0:
                                    break
                            k += 1
                        bulgu.setdefault(m.group(1), []).append((i, k + 1))
                        derinlik, i = 0, k + 1
                        continue
        i += 1
    return bulgu


_SCRIPT = re.compile(r'<script\b([^>]*)>(.*?)</script\s*>', re.S | re.I)


def _satirici(html):
    for m in _SCRIPT.finditer(html):
        if re.search(r'\bsrc\s*=', m.group(1) or '', re.I):
            continue
        yield m.start(2), m.group(2)


def _src_sirasi(html):
    for m in _SCRIPT.finditer(html):
        s = re.search(r'\bsrc\s*=\s*"([^"]*)"', m.group(1) or '', re.I)
        if s:
            yield m.start(), s.group(1)


def _oku(p):
    return p.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def app_islevleri():
    return _ustduzey(_oku(APP_JS))


def _canli_golge(app_fn):
    """app.js'i yükleyen sayfalarda, app.js'ten SONRA gelen satır içi
    bildirimlerle ezilen adlar."""
    golge = set()
    for yol in sorted(TPL.glob('*.html')):
        html = _oku(yol)
        app_konum = next((p for p, s in _src_sirasi(html)
                          if s.endswith('/app.js')), None)
        if app_konum is None:
            continue
        for blok_bas, govde in _satirici(html):
            if blok_bas <= app_konum:
                continue
            golge |= set(_ustduzey(govde)) & set(app_fn)
    return golge


class TestOHD2902Golgeleme:
    """OH-D29-02 / P12bB3-09 / OH-D28-10 / P12bS1-06 — tek onarım."""

    def test_canli_golge_kalmadi(self, app_islevleri):
        """Ölçülen 11 canlı gölgenin hiçbiri kalmamalı."""
        kume = _canli_golge(app_islevleri)
        assert kume == CANLI_GOLGE, (
            'app.js şablonun satır içi betiğince yeniden bildiriliyor: %s — '
            'her biri sessiz bir kapı kaybı adayıdır (D28 arayuz a3 dersi). '
            'Meşru bir yeniden bildirim eklendiyse CANLI_GOLGE kümesini '
            'ADIYLA güncelle; sayı yükseltme.' % sorted(kume - CANLI_GOLGE))

    def test_sokulen_olu_govdeler_geri_gelmedi(self, app_islevleri):
        """Söküm ölçümle yapıldı; kopyalar geri yazılırsa bekçi görür."""
        geri = sorted(SOKULEN & set(app_islevleri))
        assert geri == [], (
            'app.js’e D30 a1’de sökülen ölü kopyalar geri geldi: %s — '
            'bu adların canlı sürümü advanced.html satır içi betiğindedir.'
            % geri)

    def test_app_js_tek_tuketicisi_advanced(self):
        """Mekanizmanın ön koşulu ve sökümün gerekçesi ölçülür.

        ``app.js`` başka bir şablona eklenirse sökülen gövdeler o sayfada
        eksik kalabilir — bekçi bunu görür.
        """
        yukleyen = sorted(
            y.name for y in TPL.glob('*.html')
            if any(s.endswith('/app.js') for _, s in _src_sirasi(_oku(y))))
        assert yukleyen == ['advanced.html'], (
            'app.js’i yükleyen şablon kümesi değişti: %s — D30 a1 sökümü '
            '"tek tüketici advanced.html" ölçümüne dayanıyordu, yeniden '
            'ölçülmeli.' % yukleyen)

    def test_olu_pay_sifir(self, app_islevleri):
        """Gölgelenen gövdelerin app.js’teki satır payı 0 olmalı."""
        metin = _oku(APP_JS)
        kume = _canli_golge(app_islevleri)
        olu = sum(metin[a:b].count('\n') + 1
                  for ad in kume for a, b in app_islevleri[ad])
        assert olu == 0, (
            'app.js’te erişilemez %d satır var (gölgelenen: %s)'
            % (olu, sorted(kume)))


class TestOHD2902KapiYenidenBaglandi:
    """Gölgelemenin öldürdüğü fail-closed kapı canlı akışta koşmalı."""

    def test_kapi_app_jste_duruyor(self, app_islevleri):
        """TEK KAYNAK: kapı kopyalanmadı, app.js’teki gövde korundu."""
        assert 'assertParametricMatchesRequest' in app_islevleri, (
            'kapı app.js’ten kalkmış — ikinci bir kopya açılmamalı, '
            'gövde tek kaynakta durmalı')

    def test_kapi_canli_akistan_cagriliyor(self):
        """Kapının çağrısı ``runParametricAnalysis``ın BAŞARI dalında."""
        adv = _oku(TPL / 'advanced.html')
        fn = _ustduzey(adv)
        # Satır içi bloklardan runParametricAnalysis gövdesini çıkar
        govde = None
        for blok_bas, blok in _satirici(adv):
            ar = _ustduzey(blok).get('runParametricAnalysis')
            if ar:
                govde = blok[ar[0][0]:ar[0][1]]
                break
        assert govde, 'advanced.html::runParametricAnalysis bulunamadı'
        i = govde.find('assertParametricMatchesRequest(')
        assert i > 0, (
            'parametrik tarama yanıtı isteğe karşı DENETLENMİYOR — uç başka '
            'bir parametreyi/aralığı tararsa eğri yine çizilir '
            '(app.py §1087: start 4,0/end 8,0 isteği sweep_range [0,5; 3,0] '
            'üzerinde koşuyordu)')
        basari = govde.find("results.status === 'success'")
        assert 0 < basari < i, (
            'kapı başarı dalının içinde çağrılmalı; hata dalında ucun kendi '
            'metni (results.error) genel kapı iletisiyle örtülmemeli')

    def test_kapi_istegin_kendi_degerleriyle_cagriliyor(self):
        """Yankı, GÖNDERİLEN gövdenin alanlarıyla karşılaştırılmalı.

        Formdan ikinci kez okumak (ya da sabit yazmak) kapıyı kendi kendini
        doğrulayan bir döngüye çevirirdi.
        """
        adv = _oku(TPL / 'advanced.html')
        i = adv.find('assertParametricMatchesRequest(')
        cagri = adv[i:adv.find(')', i) + 1]
        for alan in ('data.param_type', 'data.param_start', 'data.param_end'):
            assert alan in cagri, (
                'kapı çağrısı %s alanını göndermiyor: %r' % (alan, cagri))


#: ÖLÇÜLDÜ (``a1/sonra_kapi.json`` → ``sessiz_yedek``): kazanan
#: ``advanced.html::runParametricAnalysis`` üç süpürme alanını boş/sayı
#: olmayan girdide sessizce sabitle ikame ediyor.
IKAME_ALANLARI = ('param_start', 'param_end', 'param_steps')

_IKAME = re.compile(
    r'(param_(?:start|end|steps))\s*:\s*isNaN\s*\([^)]*\)\s*\?\s*([0-9.]+)\s*:')


class TestOHD2902SessizYedekBorcu:
    """Gölgelemenin öldürdüğü ÜÇÜNCÜ kapı ailesi — ÖK-21 ile kilitli.

    ÖLÇÜLDÜ (``a1/once_kapi.json``, taban ``ab7cf68b``): ölü
    ``app.js::calculateParametric`` DÖRT doğrulama taşıyordu
    (``form_alani_yok``, ``sayi_degil``, ``bas_son_sirasi``,
    ``adim_bandi``) ve hiçbiri koşmuyordu. Üçü sunucuda fail-closed olarak
    ZATEN duruyor (``param_steps`` bandı, sonlu olmayan uç, dejenere
    aralık) — onlar istemciye KOPYALANMAZ (tek kaynak). Kapanmayan tek
    ayak şu: istemci boş alanı ``1.5`` / ``4.0`` / ``10`` ile ikame
    ettiği için sunucunun ``sweep_interval_not_supplied`` (422) kapısı
    HİÇ koşamıyor — kullanıcı boş bıraktığı bir aralığın eğrisini, kendi
    parametre adıyla etiketlenmiş olarak alıyor.

    BORÇ ÖDENDİ — ÖH D31 · arayuz-panel · aşama 2/3 (ÖK-21 KİLİDİ AÇILDI,
    Berke 14 Eyl 2026). ``advanced.html::runParametricAnalysis`` üç ikameyi
    (``1.5`` / ``4.0`` / ``10``) artık taşımıyor: boş alan için ANAHTAR
    GÖNDERİLMEZ (``a2/once.json`` M4 -> ``a2/sonra.json`` M4, ters-mutasyon
    ``a2/mutasyon.json``). ``xfail(strict)`` imi bu yüzden KALDIRILDI; test
    kalıcı gerileme kilidi olarak duruyor. Sayı mandalı değil, ALAN kümesi
    ölçülür.
    """

    def test_supurme_alanlari_sessizce_ikame_edilmiyor(self):
        adv = _oku(TPL / 'advanced.html')
        ar = None
        for _blok_bas, blok in _satirici(adv):
            ar = _ustduzey(blok).get('runParametricAnalysis')
            if ar:
                govde = blok[ar[0][0]:ar[0][1]]
                break
        assert ar, 'advanced.html::runParametricAnalysis bulunamadı'
        ikame = sorted({m.group(1) for m in _IKAME.finditer(govde)})
        assert ikame == [], (
            'süpürme aralığı istemcide sessizce ikame ediliyor: %s — '
            'alan boşken bile sunucuya bir sayı gidiyor, bu yüzden ucun '
            'kendi fail-closed kapısı (sweep_interval_not_supplied, 422) '
            'hiç koşamıyor' % ikame)

    def test_sunucu_kapisi_yerinde(self):
        """Borcun karşı ayağı: uç kapısı sökülmemeli.

        İstemci ikamesi kalkınca devreye girecek kapı budur; kapı
        kaybolursa borç ödenemez hâle gelir.
        """
        app_py = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
        assert 'sweep_interval_not_supplied' in app_py, (
            "/parametric-analysis ucunun 'aralık verilmedi' kapısı "
            'kalkmış — istemci ikamesinin borcu bu kapıya yazılıydı')
