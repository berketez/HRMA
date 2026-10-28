"""Faz 6 / F4 — yardımcı sayfaların (``/launch-site``, ``/formulas``) bekçileri.

Tarayıcı denetimi 3 Ağustos 2026'da bu iki sayfada on kusur ölçtü. Bu dosya
her birini **kusuru yeniden üretecek** biçimde kilitler: şablondaki ilgili
parça sökülüp ya node'da GERÇEKTEN çalıştırılır, ya da LaTeX'ten sayısal
olarak değerlendirilir. Düzeltme geri alınırsa test kırmızıya döner.

Kapatılan kalemler ve ölçülen değerler (önce -> sonra):

* **T08 (KRİTİK)** — ``launch_site.html`` aynı kapsamda İKİ ``function num``
  bildiriyordu: okuyucu ``num(id, fb)`` (:444) ve biçimlendirici ``num(v, d)``
  (:792). Hoisting'de sonuncu kazandığı için okuyucu tümüyle gölgeleniyordu;
  ``num('ls-a-bodydia', 0.15)`` → ``isFinite('ls-a-bodydia')=false`` → ``'--'``.
  Ölçüldü: "Fly this site" her denemede POST ``/api/six-dof-analysis`` → HTTP
  **422**, gövdedeki 8 alan dizge (``"dry_mass":"--7"`` imzası = ``'--'`` +
  motor atıl kütlesi 7), oynatım kapalı, apoje "--".
  Sonra: HTTP **200**, 8 alan da sayı (``dry_mass=25`` = 18+7), oynatım açık,
  apoje **15,72 km**, menzil 1,21 km.
* **T53 (ORTA)** — sol panel görünümün dibine kadar uzadığı için "Resolve site"
  düğmesi ölçek çubuğunun ALTINDA kalıyordu. Ölçüldü (1600x1000, panel dibe
  kaydırılmış): düğme y=916, örtüşme **4023 px² (%44,9)**,
  ``elementFromPoint(merkez)`` → ``ls-scalebar``, Playwright tıklaması 4 s'de
  zaman aşımı. Sonra: düğme y=836, örtüşme **0**, ``elementFromPoint`` →
  ``ls-resolve``, tıklama başarılı (g_yerel 9,79217 m/s²).
* **T54 (ORTA)** — karo göstergesi ``refreshTileUsage``'ı yalnız açılışta ve
  "Clear map cache" sonrasında çağırıyordu. Ölçüldü (önbellek boşaltılıp
  kamera 400 km altına indirildi, 8 karo diske indi): sunucu
  ``/api/tile/cache/status`` → ``{bytes: 193913, tiles: 8}`` derken ekranda
  hâlâ **"0 MB · 0 tile"**, NASA GIBS atfı ``display: none``.
  Sonra: ekranda **"0.2 MB · 8 tile"**, atıf ``display: block``.
* **T73 (DÜŞÜK)** — İngilizce arayüzde Türkçe metin:
  "Mount Everest (yüksek arazi)" -> "Mount Everest (high terrain)".
* **T76 (DÜŞÜK, kısmi)** — ``/formulas``'ta dil denetimi **vardı** ama diğer
  sayfalardan farklı tutamakla. Ölçüldü: ``#langSelect``=yok,
  ``[data-lang]``=0, ``[data-hrma-lang-select]``=1 (75x25 px, görünür).
  Sonra: ``#langSelect`` var ve mount edilen seçicinin ta kendisi
  (seçenekler en/tr). Künyedeki "UZAYTEK" markası bu dosyanın kapsamı
  dışında (sözlük ``i18n_formulas.js``).

Formül sayfası (γ=1,2 · R=350 J/kg·K · T_c=3000 K · p_e/p_c=0,01 ·
A_t=0,002 m² · p_c=4 MPa · C_d=0,97 · a=1e-4 · ṁ_ox=1 kg/s · r₀=0,05 m):

* **T26 (CİDDİ)** — §1.3 C_F: karekök yalnız 2γ²/(γ−1) kesrini kapsıyordu ->
  çarpımın tamamını kapsar. **0,9736 -> 1,6445** (sayfanın kendi tablosu
  1,2-2,0 diyor; C_F yakınsak-ıraksak lülede 1'in altına inemez).
* **T27 (CİDDİ)** — §1.2 c*: √(γRT_c/γ) yazılmıştı, γ sadeleşiyordu ->
  √(RT_c/γ). **1730,8 -> 1580,0 m/s**; aynı bölümün Γ kutusu ve
  ``heat_transfer_analysis.py:474`` de 1580,0 diyor (sapma √γ = %9,5).
* **T28 (CİDDİ)** — §6.2 r(t) üssü 2(1−n) -> **2n+1**. n=0,8 t=10 s:
  0,05007 -> 0,08105 m (eski yazım −%38,2); n=1'de eski üs sıfıra bölüyordu.
  §6.1 ṙ_avg kutusu da aynı (1−n) kalıbını taşıyordu (−%28,4) -> integralin
  gerçek ortalaması.
* **T29 (CİDDİ)** — §3.4 ikinci kutu η_c = 1 − (T_wall−T_gas)/T_ad idi;
  T_wall < T_gas olduğu için **1,688 / 1,600 / 1,829** (yani %169-183) veriyordu.
  -> üstteki kutuyla tutarlı √(T_act/T_ad): **0,968 / 0,966 / 0,986**.
* **T55 (ORTA)** — §1.5 1. ve 3. kutu boyutsal olarak tutarsızdı (kg/m ve
  kg^0,5·m^0,5). 1. kutuda boğaz ses hızı çarpanı yoktu, 3. kutuda p_c kökün
  içindeydi. -> ideal **5,0632 kg/s** ve C_d'li **4,9113 kg/s**; oran 1,0309
  = 1/C_d.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCH_SITE = REPO_ROOT / 'hrma' / 'templates' / 'launch_site.html'
FORMULAS = REPO_ROOT / 'hrma' / 'templates' / 'formulas.html'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')

# Denetimin kullandığı referans girdiler (bkz. modül başlığı).
GAMMA, R_GAS, T_C = 1.2, 350.0, 3000.0
PE_PC = 0.01
A_T, P_C, C_D = 0.002, 4.0e6, 0.97


@pytest.fixture(scope='module')
def ls_html():
    return LAUNCH_SITE.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def fx_html():
    return FORMULAS.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Ortak sökme yardımcıları
# ---------------------------------------------------------------------------
def inline_script(html):
    """Şablonun en uzun ``<script>`` gövdesi (sayfanın kendi IIFE'si)."""
    parcalar = re.findall(r'<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>',
                          html, re.S)
    assert parcalar, 'şablonda gömülü <script> yok'
    return max(parcalar, key=len)


def yorumsuz(js):
    """Tam satır ve blok yorumları at — ad taraması yorum metnine takılmasın."""
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    return '\n'.join(s for s in js.split('\n') if not s.lstrip().startswith('//'))


def blok_sok(kaynak, bas):
    """``bas`` ile başlayan ifadeyi süslü parantez dengeleyerek söker."""
    i = kaynak.index(bas)
    j = kaynak.index('{', i)
    derinlik, k = 0, j
    while k < len(kaynak):
        if kaynak[k] == '{':
            derinlik += 1
        elif kaynak[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                break
        k += 1
    return kaynak[i:k + 1]


def sqrt_kapsami(latex, sira=0):
    """``\\sqrt{...}`` kapsamındaki metni süslü parantez dengeleyerek döndürür."""
    bulunan, ara = [], 0
    while True:
        i = latex.find(r'\sqrt{', ara)
        if i < 0:
            break
        j = i + len(r'\sqrt{')
        derinlik, k = 1, j
        while k < len(latex) and derinlik:
            if latex[k] == '{':
                derinlik += 1
            elif latex[k] == '}':
                derinlik -= 1
            k += 1
        bulunan.append(latex[j:k - 1])
        ara = k
    assert len(bulunan) > sira, r'beklenen \sqrt{...} yok: ' + latex[:90]
    return bulunan[sira]


def formul_kutulari(html, baslik_on_eki):
    """``<h3>`` başlığından sonraki, bir sonraki başlığa kadarki formül kutuları."""
    m = re.search(r'<h3[^>]*>\s*' + re.escape(baslik_on_eki) + r'[^<]*</h3>(.*?)'
                  r'(?=<h3|<h2|</div>\s*\n\s*<!--\s*Section)', html, re.S)
    assert m, 'bölüm bulunamadı: ' + baslik_on_eki
    # ÖH D29 · arayuz-panel a2: desen ÖZNİTELİKSİZ kutuyla sınırlıydı.
    # ÖH D29 a1/a2 model-farkı beyanları kutulara `data-model-gap="…"`
    # ekleyince §6.1'in üçüncü kutusu listeden DÜŞÜYOR ve indis taşıyordu
    # (IndexError). Yardımcının niyeti "formül kutuları"dır, "özniteliksiz
    # formül kutuları" değil — desen özniteliğe toleranslı hâle getirildi.
    # Kusuru koruyan bir bekçi değildi; kırılganlıktı.
    return [re.sub(r'\s+', ' ', k).strip()
            for k in re.findall(r'<div class="formula-box"[^>]*>(.*?)</div>',
                                m.group(1), re.S)]


def lateks_sayiya(ifade, degerler):
    """Küçük LaTeX alt kümesini Python ifadesine çevirip sayısal değerlendirir.

    Yalnız bu dosyadaki kutularda geçen yapıları tanır: ``\\frac``, ``\\sqrt``,
    ``\\left(``/``\\right)``, ``^{...}`` ve bilinen semboller. Tanımadığı bir
    şey kalırsa AssertionError atar — sessizce yanlış sayı üretmez.
    """
    s = ifade
    s = s.replace(r'\left', '').replace(r'\right', '')
    s = s.replace(r'\,', ' ').replace(r'\!', '')
    # LaTeX'te [ ] yalnız görsel parantezdir; Python'da dizin olmasın
    s = s.replace('[', '(').replace(']', ')')
    # \frac{A}{B} -> ((A)/(B))  (içten dışa, yinelemeli)
    while r'\frac{' in s:
        i = s.index(r'\frac{')
        pay, k = _sus_al(s, i + len(r'\frac{') - 1)
        payda, k2 = _sus_al(s, k)
        s = s[:i] + '((' + pay + ')/(' + payda + '))' + s[k2:]
    while r'\sqrt{' in s:
        i = s.index(r'\sqrt{')
        ic, k = _sus_al(s, i + len(r'\sqrt{') - 1)
        s = s[:i] + '__sqrt((' + ic + '))' + s[k:]
    # ^{...} -> **(...)
    while '^{' in s:
        i = s.index('^{')
        ic, k = _sus_al(s, i + 1)
        s = s[:i] + '**(' + ic + ')' + s[k:]
    s = re.sub(r'\^(\w)', r'**\1', s)
    for ad, deger in degerler.items():
        s = s.replace(ad, '(' + repr(float(deger)) + ')')
    s = s.replace('{', '(').replace('}', ')')
    # Örtük çarpım: ")(" ve ")sayı" gibi bitişiklikleri açıkla
    s = re.sub(r'\)\s*\(', ')*(', s)
    s = re.sub(r'(\d)\s*\(', r'\1*(', s)
    s = re.sub(r'\)\s*(\d)', r')*\1', s)
    kalan = re.findall(r'[A-Za-z\\]+', s.replace('__sqrt', ''))
    assert not kalan, 'çevrilemeyen sembol kaldı: %r  (%s)' % (kalan, s)
    return eval(s, {'__builtins__': {}, '__sqrt': math.sqrt})   # noqa: S307


def _sus_al(s, acilis_oncesi):
    """``s[acilis_oncesi]`` '{' olacak şekilde dengeli grubu ve bitiş indisini döndür."""
    i = s.index('{', acilis_oncesi)
    derinlik, k = 0, i
    while k < len(s):
        if s[k] == '{':
            derinlik += 1
        elif s[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return s[i + 1:k], k + 1
        k += 1
    raise AssertionError('dengelenmemiş süslü parantez')


# ===========================================================================
# T08 — "Fly this site": iki num() bildirimi 8 alanı dizgeye çeviriyordu
# ===========================================================================
class TestT08UcusGovdesi:
    """Gövde kurulumu node'da GERÇEKTEN çalıştırılır (hoisting dahil)."""

    # --- ÖH D30 / fix-29a — SAYIM MANDALI KÜME ÖLÇÜSÜNE ÇEVRİLDİ ---------
    # Bu sınıfın iki bekçisi ``== 8`` diye SAYIYORDU. D28 arayüz a4 iki
    # meşru rüzgâr girdisi ekleyince (``ls-a-windspeed`` / ``ls-a-winddir``)
    # sayı 10'a çıktı ve ikisi de kırmızıya döndü — oysa korudukları kusur
    # (alanın dizge gitmesi, okuyucu ile biçimlendiricinin karışması) hiç
    # doğmamıştı. Sayıyı 10'a YÜKSELTMEK mandalı bir sonraki meşru alanda
    # yine kıracaktı ve arada eksilen bir alanı göremezdi. Ölçü artık KÜME:
    # okunan alanlar ile şablonun varsayılanlı alanları BİREBİR aynı kümedir;
    # yeni alan ikisini birlikte büyütür, biri eksik kalırsa kırmızı yanar.
    # (D27 dersi 11: sayım bekçisi değil ilişki bekçisi.)

    @staticmethod
    def _sablon_alanlari(html):
        """Şablondaki ``ls-a-*`` girdileri: {id: varsayılan} (uydurma yok)."""
        return dict(re.findall(
            r'id="(ls-a-[a-z0-9]+)"[^>]*value="([^"]+)"', html))

    @staticmethod
    def _okunan_alanlar(js):
        r"""JS'in ``fieldNum`` ile GERÇEKTEN okuduğu id'ler (bildirim değil).

        V301/UÇUŞ C-25: ``fieldNum`` artık TEK argümanlıdır (yedek sayı
        parametresi söküldü — boş alan null döner ve gönderilmez); eski
        ``fieldNum\((.*?),`` deseni yedek argümanının virgülüne dayanıyordu.
        İlk argüman (id) okunur; çağrının biçimi değişse de küme ölçüsü aynı.
        """
        return [c.strip().strip("'\"")
                for c in re.findall(r'(?<!function )fieldNum\(\s*([^,)]*)', js)]

    @classmethod
    def _kume_esitligi(cls, html):
        """Şablon ⟷ okuyucu küme eşitliği; iki yönlü, sayısız."""
        sablon = cls._sablon_alanlari(html)
        okunan = cls._okunan_alanlar(yorumsuz(inline_script(html)))
        yinelenen = sorted({a for a in okunan if okunan.count(a) > 1})
        assert not yinelenen, 'aynı alan iki kez okunuyor: %r' % yinelenen
        assert set(okunan) == set(sablon), (
            'şablon ile okuyucu ayrıştı — şablonda olup okunmayan: %s; '
            'okunup şablonda varsayılanı olmayan: %s'
            % (sorted(set(sablon) - set(okunan)),
               sorted(set(okunan) - set(sablon))))
        return sablon, okunan

    @classmethod
    def _harness(cls, html):
        js = inline_script(html)
        # Sayı yardımcılarının TAMAMI, dosyadaki SIRAYLA — hoisting'i birebir
        # yeniden üretmek şart: kusurlu sürümde iki bildirim de 'num' adındaydı.
        bildirimler = re.findall(
            r'^\s*(function (?:num_?|fieldNum|fmtNum)\(.*\}\s*)$', js, re.M)
        assert len(bildirimler) >= 3, bildirimler
        dry = re.search(r'^\s*(var dryTotal = .*;)\s*$', js, re.M)
        assert dry, 'dryTotal satırı bulunamadı'
        # ÖH D33-KOLAY · P12bB4-05: uçuş yükü artık beş gövde sabitini
        # ŞABLONDAKİ TEK NESNEDEN (`LS_FIXED_AIRFRAME`) okuyor. Koşum ikizi
        # nesneyi de sökmeli; yoksa `ReferenceError` ile patlar. Nesne
        # ŞABLONDAN okunur, teste GÖMÜLMEZ (tek kaynak korunur).
        sabitler = blok_sok(js, 'var LS_FIXED_AIRFRAME = ') + ';'
        govde = blok_sok(js, 'var body = ')
        # Girdi varsayılanları ŞABLONUN KENDİSİNDEN okunur (uydurma yok).
        alanlar, _ = cls._kume_esitligi(html)
        return """
        'use strict';
        var DOM = %s;
        function el(id) { return DOM.hasOwnProperty(id) ? {value: DOM[id]} : undefined; }
        var veh = {propellant_mass: 18, thrust: 6500, burn_time: 7.5,
                   engine_inert_mass: 7};
        var la = 28.6084;
        %s
        %s
        %s
        %s
        console.log(JSON.stringify(body));
        """ % (json.dumps(alanlar), '\n'.join(bildirimler), sabitler,
                 dry.group(1), govde)

    @needs_node
    def test_gonderilen_alanlar_sayidir(self, ls_html):
        """Kusurlu sürümde bu 8 alan '--' dizgesiydi ve sunucu 422 dönüyordu."""
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(self._harness(ls_html))
            yol = f.name
        cikti = subprocess.run(['node', yol], capture_output=True, text=True,
                               timeout=30)
        assert cikti.returncode == 0, cikti.stderr
        body = json.loads(cikti.stdout.strip())

        # Gövdenin HANGİ anahtarları alandan besleniyor — ŞABLONDAN ve
        # gövde bloğundan okunur, elle listelenmez (yeni alan eklenince
        # bu bekçi kendiliğinden onu da sınar).
        sablon = self._sablon_alanlari(ls_html)
        js = yorumsuz(inline_script(ls_html))
        eslesme = dict(
            (anahtar, alan) for anahtar, alan in re.findall(
                r"(\w+):\s*fieldNum\('(ls-a-[a-z0-9]+)'", js))
        assert eslesme, 'gövdede fieldNum ile beslenen anahtar yok'
        olculen = sorted(eslesme) + ['dry_mass']
        dizgeler = {k: body[k] for k in olculen if isinstance(body[k], str)}
        assert not dizgeler, 'dizge olarak giden alanlar (422 sebebi): %r' % dizgeler
        # Şablondaki varsayılanların TA KENDİSİ (sayı teste kopyalanmaz).
        for anahtar, alan in sorted(eslesme.items()):
            assert body[anahtar] == pytest.approx(float(sablon[alan])), (
                '%s şablon varsayılanıyla (%s=%s) uyuşmuyor: %r'
                % (anahtar, alan, sablon[alan], body[anahtar]))
        # ÇİFT SAYIM sözleşmesi: gövde kurusu + motor atılı (18 + 7)
        assert body['dry_mass'] == pytest.approx(
            float(sablon['ls-a-drymass']) + 7), (
            "kusurlu sürümdeki imza '--7' idi")
        assert '--' not in json.dumps(body)

    def test_ayni_ada_iki_bildirim_yok(self, ls_html):
        """Kök neden sınıfı: aynı kapsamda iki kez bildirilen fonksiyon adı."""
        js = yorumsuz(inline_script(ls_html))
        adlar = re.findall(r'^\s{0,8}function (\w+)\s*\(', js, re.M)
        tekrar = sorted({a for a in adlar if adlar.count(a) > 1})
        assert not tekrar, 'aynı kapsamda birden çok kez bildirilen ad: %r' % tekrar

    def test_okuyucu_ve_bicimlendirici_ayrisik(self, ls_html):
        """Okuyucu id ile, biçimlendirici değerle çağrılmalı; karışmamalı."""
        js = yorumsuz(inline_script(ls_html))
        assert not re.search(r'[^\w.]num\s*\(', js), 'çıplak num( çağrısı kaldı'
        # (?<!function ) → bildirim satırlarını değil, ÇAĞRILARI süz
        cagrilar = re.findall(r'(?<!function )fieldNum\(\s*([^,)]*)', js)
        # Sayı yerine KÜME: okuyucunun gördüğü alanlar şablonunkilerle bire
        # bir aynı olmak zorunda (iki yönlü; yeni alan ikisini birlikte
        # büyütür).
        self._kume_esitligi(ls_html)
        for cagri in cagrilar:
            assert cagri.strip().startswith("'ls-"), \
                'fieldNum id ile çağrılmalı: %r' % cagri
        for cagri in re.findall(r'(?<!function )fmtNum\((.*?),', js):
            assert not cagri.strip().startswith("'"), \
                'fmtNum değerle çağrılmalı, dizge id ile değil: %r' % cagri


# ===========================================================================
# T53 — "Resolve site" düğmesi ölçek çubuğunun altında kalıyordu
# ===========================================================================
class TestT53AltSeritPayi:

    def test_paneller_alt_kutulara_pay_birakir(self, ls_html):
        """max-height alt şerit payını DÜŞMELİ; yoksa panel çubuğun üstüne biner."""
        for pid, degisken in (('ls-left', '--ls-reserve-left'),
                              ('ls-right', '--ls-reserve-right')):
            m = re.search(r'#' + pid + r'\s*\{([^}]*)\}', ls_html)
            assert m, pid + ' kuralı yok'
            kural = m.group(1)
            mh = re.search(r'max-height:\s*([^;]+);', kural)
            assert mh, pid + ' için max-height yok'
            assert 'var(' + degisken + ')' in mh.group(1), (
                '%s max-height alt şerit payını düşmüyor: %r'
                % (pid, mh.group(1)))

    def test_pay_gercek_kutu_yuksekliginden_olculur(self, ls_html):
        """Sabit sayı değil: ölçek çubuğu/notların GERÇEK yüksekliği okunmalı."""
        js = inline_script(ls_html)
        fn = blok_sok(js, 'function layoutBottomReserve')
        assert "el('ls-scalebar')" in fn and "el('ls-notes')" in fn
        assert fn.count('offsetHeight') >= 2, 'yükseklik ölçülmüyor'
        assert "setProperty('--ls-reserve-left'" in fn
        assert "setProperty('--ls-reserve-right'" in fn
        # Yeniden ölçüm tetikleyicileri: açılış + pencere boyu + düzenli tik
        assert re.search(r"addEventListener\('resize', layoutBottomReserve\)", js)
        assert 'layoutBottomReserve();' in js

    def test_periyodik_tik_erken_cikistan_once_calisir(self, ls_html):
        """getScaleInfo() null dönse de yerleşim/karo işleri yapılmalı."""
        js = inline_script(ls_html)
        tik = js[js.index('setInterval(function'):]
        tik = tik[:tik.index('}, 150);')]
        yerlesim = tik.index('layoutBottomReserve();')
        karo = tik.index('watchTiles();')
        erken_cikis = tik.index('if (!info) return;')
        assert yerlesim < erken_cikis and karo < erken_cikis, \
            'layoutBottomReserve/watchTiles erken çıkışın ARDINDA kalmış'


# ===========================================================================
# T54 — karo göstergesi indirme sonrası yenilenmiyordu, atıf hiç görünmüyordu
# ===========================================================================
class TestT54KaroGostergesi:

    def test_gosterge_karo_durumu_degisince_yenilenir(self, ls_html):
        js = inline_script(ls_html)
        fn = blok_sok(js, 'function watchTiles')
        assert 'getTileInfo' in fn, 'küre modülünün gerçek karo durumu okunmuyor'
        assert 'refreshTileUsage()' in fn, 'durum değişince gösterge yenilenmiyor'
        assert 'watchTiles();' in js, 'watchTiles hiç çağrılmıyor'

    def test_atif_ekrandaki_karoya_bagli(self, ls_html):
        """Atıf, GIBS görüntüsü ekrandayken görünmeli — disk sayısına göre değil.

        ÖH D21 / P12aB4-19 (kalıp gevşetildi, sözleşme AYNI): görünürlük
        ölçütü hâlâ küre durumudur (`info.active`), ama artık ek olarak
        katmanın künye ANAHTARI da aranır — anahtar yoksa atıf hiç basılmaz
        (başka katmanın künyesi gösterilmesin diye, fail-closed). Düğüm de
        değişkene alındı (aynı düğüme iki kez `setAttribute` yapılıyor).
        Eski kalıp `el('ls-tile-attr').style.display = info.active` metnini
        BİREBİR arıyordu; korunan davranış değil yazım biçimiydi. Yeni kalıp
        düğümün gerçekten `ls-tile-attr` olduğunu ayrıca doğrular.
        """
        js = inline_script(ls_html)
        fn = blok_sok(js, 'function watchTiles')
        assert re.search(r"var attrEl = el\('ls-tile-attr'\);", fn), \
            'atıf düğümü watchTiles içinde çözülmüyor'
        assert re.search(r"(?:attrEl|el\('ls-tile-attr'\))\.style\.display"
                         r"\s*=\s*[^;]*\binfo\.active\b", fn), \
            'atıf görünürlüğü küre durumundan sürülmüyor'
        yenile = blok_sok(js, 'function refreshTileUsage')
        assert 'ls-tile-attr' not in yenile, (
            'atıf hâlâ disk önbelleği sayısından sürülüyor (kusurlu davranış)')

    def test_gosterge_metni_sunucudan_gelir(self, ls_html):
        """Ekrandaki sayı uydurulmaz: doğrudan /api/tile/cache/status'tan."""
        js = inline_script(ls_html)
        yenile = blok_sok(js, 'function refreshTileUsage')
        assert "fetch('/api/tile/cache/status')" in yenile
        assert 'd.bytes' in yenile and 'd.tiles' in yenile


# ===========================================================================
# T73 — İngilizce arayüzde Türkçe metin
# ===========================================================================
class TestT73KisayolDili:
    """ÇEVRİLDİ (ÖH D24 · P4B3-27). Eski hâli KUSURU KORUYORDU.

    Eski üç test şablondaki ``var PRESETS = [ ... ]`` gömülü dizisini
    metin olarak sökuyor, 7 kaydı ve koordinatlarını orada arıyordu —
    yani P4B3-27'nin kusurunu (arayüzün Python listesinden BAĞIMSIZ
    kendi kopyası) kilitliyordu: liste tek kaynağa bağlandığı anda
    ``js.index('var PRESETS = [')`` ValueError atıyor.

    Testlerin KORUDUĞU niyet aynen sürüyor, yalnız ölçüm noktası kaydı:
    dil sızıntısı artık TEK KAYNAKTA (``LAUNCH_SITE_PRESETS``) ve
    şablonun arazi referansında aranır; koordinatlar da o kaynaktan
    doğrulanır. Kopya olmadığı için "iki liste ayrıştı" hatası artık
    yapısal olarak imkânsız.
    """

    TURKCE = set('çğıİöşüÇĞÖŞÜ')

    def _terrain_refs(self, ls_html):
        """Şablonun arazi referansı dizisi (fırlatma sahası DEĞİL)."""
        js = inline_script(ls_html)
        dizi = js[js.index('var TERRAIN_REFS = ['):]
        return dizi[:dizi.index('];') + 2]

    def test_kisayol_etiketleri_turkce_icermez(self, ls_html):
        """İngilizce arayüzde Türkçe ad sızmasın (T73'ün kendi niyeti)."""
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        etiketler = [p['name'] for p in LAUNCH_SITE_PRESETS]
        etiketler += re.findall(r"name:\s*'([^']+)'", self._terrain_refs(ls_html))
        assert len(etiketler) == len(LAUNCH_SITE_PRESETS) + 1, etiketler
        for e in etiketler:
            sizan = self.TURKCE & set(e)
            assert not sizan, 'İngilizce listede Türkçe karakter: %r (%r)' % (e, sizan)
        assert 'Mount Everest' in etiketler

    def test_etiketler_i18n_uzerinden_basilir(self, ls_html):
        """Anahtarlı girdi t() ile çözülmeli ve dil değişince tazelenmeli."""
        js = inline_script(ls_html)
        assert re.search(r'function presetLabel\(p\)\s*\{[^}]*t\(p\.i18nKey', js)
        assert 'relabelPresets()' in js.split('I18N.onChange')[-1]

    def test_yaklasik_kayit_ekranda_ayriliyor(self, ls_html):
        """ÖH D24 · P4B3-27: ``approx`` bayrağı ETİKETE ulaşır.

        Python listesi 'Sinop (TR)' ve 'Konya (TR)' kayıtlarını
        ``approx: True`` ile işaretliyor ("gerçek bir tesis değil, bölge
        referansı"); bu ayrım ekranda söylenmezse kullanıcı onları KSC
        LC-39A ile aynı sınıfta görür.
        """
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        assert sum(1 for p in LAUNCH_SITE_PRESETS if p['approx']) >= 1
        js = inline_script(ls_html)
        etiket = blok_sok(js, 'function presetLabel')
        assert 'p.approx' in etiket
        assert 'site.presetApprox' in etiket
        assert 'p.terrain' in etiket and 'site.presetTerrainRef' in etiket

    def test_liste_sunucudan_geliyor_kopya_yok(self, ls_html):
        """Şablon kendi saha listesini TAŞIMAZ; rotadan alır."""
        # Veri JSON script etiketinde durur; gömülü JS onu okur (böylece
        # betik saf JavaScript kalır ve node --check ayrıştırabilir).
        assert ('<script type="application/json" id="ls-presets-data">'
                '{{ launch_site_presets | tojson }}</script>') in ls_html
        js = inline_script(ls_html)
        assert "document.getElementById('ls-presets-data')" in js
        # Gömülü koordinat dizisi geri gelmesin (eski kusurun imzası)
        assert not re.search(r"\[\s*'[a-z_]+',\s*'[^']+',\s*-?\d+\.\d+,\s*-?\d+\.\d+", js)

    def test_koordinatlar_korundu(self, ls_html):
        """Etiket düzeltmesi koordinatlara dokunmamalı (denetimde doğrulanmıştı).

        Artık TEK KAYNAKTAN doğrulanır: eski gömülü dizideki dört kayıt
        Python listesinde birebir aynı koordinatlarla duruyor (everest
        fırlatma sahası olmadığı için şablonun arazi referansında).
        """
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        koordinatlar = dict(
            (p['id'], (p['latitude'], p['longitude'])) for p in LAUNCH_SITE_PRESETS)
        assert koordinatlar['ksc_lc39a'] == (28.6084, -80.6043)
        assert koordinatlar['sinop_tr'] == (42.0231, 35.1531)
        assert koordinatlar['mahia_lc1'] == (-39.2617, 177.8650)
        arazi = self._terrain_refs(ls_html)
        assert re.search(r'latitude:\s*27\.9881', arazi)
        assert re.search(r'longitude:\s*86\.9250', arazi)



# ===========================================================================
# T76 — /formulas dil denetimi diğer sayfalarla aynı tutamağı taşımalı
# ===========================================================================
class TestT76DilDenetimi:

    def test_mount_edilen_secici_langSelect_kimligini_alir(self, fx_html):
        js = inline_script(fx_html)
        assert 'mountSwitcher' in js, 'dil seçici hiç mount edilmiyor'
        assert re.search(r"sel\.id\s*=\s*'langSelect'", js), (
            'seçici ana sayfayla aynı tutamağı (#langSelect) almıyor')


# ===========================================================================
# Formül sayfası — sayısal bekçiler
# ===========================================================================
class TestT26ItkiKatsayisi:

    def test_karekok_carpimin_tamamini_kapsar(self, fx_html):
        kutu = formul_kutulari(fx_html, '1.3')[0]
        kapsam = sqrt_kapsami(kutu)
        for parca in (r'\frac{2\gamma^2}{\gamma-1}', r'\frac{2}{\gamma+1}',
                      r'\frac{p_e}{p_c}'):
            assert parca in kapsam, (
                'karekök kapsamı eksik (%s dışarıda): %r' % (parca, kapsam))

    def test_CF_fiziksel_bantta(self, fx_html):
        """Sayfanın kendi tablosu 1,2-2,0 diyor; kusurlu yazım 0,9736 veriyordu."""
        kutu = formul_kutulari(fx_html, '1.3')[0]
        deger = lateks_sayiya(sqrt_kapsami(kutu), {
            r'\gamma': GAMMA, 'p_e': PE_PC, 'p_c': 1.0})
        cf = math.sqrt(deger)
        assert cf == pytest.approx(1.6445, abs=1e-3), cf
        assert 1.2 <= cf <= 2.0, 'C_F sayfanın kendi tipik bandının dışında'


class TestT27KarakteristikHiz:

    def test_gamma_paydada(self, fx_html):
        kutu = formul_kutulari(fx_html, '1.2')[0]
        kapsam = sqrt_kapsami(kutu)
        m = re.match(r'\\frac\{(.+)\}\{(.+)\}$', kapsam)
        assert m, kapsam
        pay, payda = m.group(1), m.group(2)
        assert r'\gamma' not in pay, 'γ pay ve paydada sadeleşiyor: %r' % kapsam
        assert payda.strip() == r'\gamma'

    def test_iki_kutu_ayni_sayiyi_verir(self, fx_html):
        """Aynı büyüklüğü tanımlayan iki kutu %9,5 (=√γ) çelişiyordu."""
        kutular = formul_kutulari(fx_html, '1.2')
        deg = {r'\gamma': GAMMA, 'R': R_GAS, 'T_c': T_C}
        k1 = (math.sqrt(lateks_sayiya(sqrt_kapsami(kutular[0]), deg))
              * ((GAMMA + 1) / 2) ** ((GAMMA + 1) / (2 * (GAMMA - 1))))
        gamma_buyuk = math.sqrt(GAMMA) * (2 / (GAMMA + 1)) ** (
            (GAMMA + 1) / (2 * (GAMMA - 1)))
        k2 = math.sqrt(R_GAS * T_C) / gamma_buyuk
        assert k1 == pytest.approx(k2, rel=1e-9), (
            'kutu1=%.1f  kutu2=%.1f  oran=%.4f' % (k1, k2, k1 / k2))
        assert k1 == pytest.approx(1580.0, abs=0.5)


class TestT55KutleDebisi:

    def test_birinci_kutuda_hiz_carpani_var(self, fx_html):
        """Eski yazımda √(RT_c) yoktu; birim kg/m çıkıyordu."""
        kutu = formul_kutulari(fx_html, '1.5')[0]
        kapsam = sqrt_kapsami(kutu)
        deger = lateks_sayiya(kapsam, {r'\gamma': GAMMA, 'R': R_GAS, 'T_c': T_C})
        a_yildiz = math.sqrt(deger)
        beklenen = math.sqrt(2 * GAMMA * R_GAS * T_C / (GAMMA + 1))
        assert a_yildiz == pytest.approx(beklenen, rel=1e-9), a_yildiz
        rho_t = P_C / (R_GAS * T_C) * (2 / (GAMMA + 1)) ** (1 / (GAMMA - 1))
        assert rho_t * A_T * a_yildiz == pytest.approx(5.0632, abs=1e-3)

    def test_ucuncu_kutuda_pc_kokun_disinda(self, fx_html):
        """Eski yazımda p_c karekökün İÇİNDEYDİ; birim kg^0,5·m^0,5 çıkıyordu."""
        kutu = formul_kutulari(fx_html, '1.5')[2]
        kapsam = sqrt_kapsami(kutu)
        assert 'p_c' not in kapsam, 'p_c hâlâ karekökün içinde: %r' % kapsam
        assert re.search(r'C_d\s*A_t\s*p_c', kutu), (
            'p_c doğrusal çarpan olarak yazılmamış: %r' % kutu)
        deger = lateks_sayiya(kapsam, {r'\gamma': GAMMA, 'R': R_GAS, 'T_c': T_C})
        mdot = (C_D * A_T * P_C * math.sqrt(deger)
                * (2 / (GAMMA + 1)) ** ((GAMMA + 1) / (2 * (GAMMA - 1))))
        assert mdot == pytest.approx(4.9113, abs=1e-3), mdot


class TestT29YanmaVerimi:

    UCLULER = [(800, 3000, 3200), (1000, 2800, 3000), (500, 3400, 3500)]

    def test_verim_birin_ustune_cikamaz(self, fx_html):
        """Eski yazım aynı üçlülerde 1,688 / 1,600 / 1,829 veriyordu."""
        kutu = formul_kutulari(fx_html, '3.4')[1]
        assert 'T_{wall}' not in kutu and 'T_{gas}' not in kutu, (
            'cidar−gaz farkı tanımı geri gelmiş: %r' % kutu)
        kapsam = sqrt_kapsami(kutu)
        for _t_w, t_gaz, t_ad in self.UCLULER:
            eta = math.sqrt(lateks_sayiya(
                kapsam, {'T_{c,actual}': t_gaz, 'T_{c,adiabatic}': t_ad}))
            assert eta <= 1.0, 'η_c = %.3f > 1 (fiziksel olarak imkânsız)' % eta
            assert eta == pytest.approx(math.sqrt(t_gaz / t_ad), rel=1e-9)

    def test_ust_kutuyla_tutarli(self, fx_html):
        """c* ∝ √T_c olduğundan sıcaklık biçimi c* oranının KAREKÖKÜ olmalı."""
        kutular = formul_kutulari(fx_html, '3.4')
        assert 'c^*_{actual}' in kutular[0]
        # Kusurlu sürümde ikinci kutuda karekök YOKTU (1 − ΔT/T_ad biçimi).
        kapsam = sqrt_kapsami(kutular[1])
        m = re.match(r'\\frac\{(.+)\}\{(.+)\}$', kapsam)
        assert m, 'ikinci kutu sıcaklık ORANININ karekökü değil: %r' % kapsam
        pay, payda = m.group(1).strip(), m.group(2).strip()
        assert pay.startswith('T_') and payda.startswith('T_'), (pay, payda)
        assert 'adiabatic' in payda, 'paydada adyabatik alev sıcaklığı olmalı'
        assert math.sqrt(2800 / 3000) == pytest.approx(0.9661, abs=1e-4)


class TestT28PortYaricapi:

    def test_us_2n_arti_1(self, fx_html):
        """Eski üs 2(1−n) idi; n=1'de payda sıfırlanıp ifade tanımsız oluyordu."""
        kutu = formul_kutulari(fx_html, '6.2')[1]
        m = re.search(r'r_0\^\{(.+?)\}', kutu)
        assert m, kutu
        us_metni = m.group(1)
        for n in (0.3, 0.5, 0.8, 1.0):
            us = lateks_sayiya(us_metni, {'n': n})
            assert us == pytest.approx(2 * n + 1), (
                'n=%s için üs %s (beklenen %s)' % (n, us, 2 * n + 1))
        assert '2(1-n)' not in kutu.replace(' ', '')

    def test_r_of_t_odenin_cozumu(self, fx_html):
        """ṙ = a(ṁ_ox/(πr²))^n integrali: r^(2n+1) = r₀^(2n+1) + (2n+1)a(ṁ/π)^n t."""
        kutu = formul_kutulari(fx_html, '6.2')[1]
        us = lateks_sayiya(re.search(r'r_0\^\{(.+?)\}', kutu).group(1), {'n': 0.8})
        a, mox, r0, t = 1e-4, 1.0, 0.05, 10.0
        r_sayfa = (r0 ** us + us * a * (mox / math.pi) ** 0.8 * t) ** (1 / us)
        assert r_sayfa == pytest.approx(0.08105, abs=1e-5), r_sayfa
        # Kusurlu yazımın verdiği değer (kayıt için): 0,05007 m → −%38,2
        assert r_sayfa > 0.07, 'kusurlu 2(1−n) yazımına dönülmüş olabilir'

    def test_ortalama_regresyon_integralden_gelir(self, fx_html):
        """§6.1 ṙ_avg kutusu da aynı (1−n) kalıbını taşıyordu (−%28,4)."""
        kutu = formul_kutulari(fx_html, '6.1')[2]
        assert r'\frac{a G_{ox}^n}{1-n}' not in kutu.replace(' ', ''), kutu
        assert '{1-n}' not in kutu.replace(' ', ''), (
            'n=1 için sıfıra bölen (1−n) paydası geri gelmiş: %r' % kutu)
        assert 'r_f - r_0' in kutu and 't_b' in kutu
        assert '2n+1' in kutu.replace(' ', '')
