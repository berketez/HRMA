"""ÖH Dalga-34 · kulvar ``kabuk-erisilebilirlik`` · aşama a1.

21 Eylül 2026 görsel kabul turunda (Cowork) çıkan yedi kabuk/erişilebilirlik
kusurunun bekçileri. Her bekçi, ölçülmüş bir kusuru görür: kanıt dizini
``docs/scofield/raw/OH/D34/kabuk-erisilebilirlik/a1/`` (``once.json`` ⟷
``sonra.json`` ve ``mutasyon*.json``).

Bekçilerin ortak ilkesi: MÜMKÜNSE DAVRANIŞ ÖLÇÜLÜR, kaynak dizesi değil.
  * CSS için basamak (özgüllük + kaynak sırası) çözülür — "kural dosyada
    sonra yazılmış" bir ayrışma kanıtı DEĞİLDİR (OH-GT-12'nin dersi).
  * Güvertenin red metni için çeviri katmanı ``node`` içinde koşturulup
    ekrana gerçekten ne düştüğü okunur.
  * Katalog adları ürünün kendi kayıtlarından okunur.
"""
import json
import os
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D34',
                     'kabuk-erisilebilirlik', 'a1')


def _oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


# ===========================================================================
# CSS basamak çözücü — OH-GT-12'nin bekçisi bunun üstünde durur.
# ===========================================================================
_KURAL = re.compile(r'([^{}]+)\{([^{}]*)\}')
_YORUM = re.compile(r'/\*.*?\*/', re.S)


def _css_temizle(css):
    """Yorumları ve @-bloklarını söker (bkz. a1/olcum.py ``_temizle``)."""
    css = _YORUM.sub(' ', css)
    cikti, i, n = [], 0, len(css)
    while i < n:
        j = css.find('@', i)
        if j < 0:
            cikti.append(css[i:])
            break
        cikti.append(css[i:j])
        k = css.find('{', j)
        if k < 0:
            break
        derinlik = 0
        while k < n:
            if css[k] == '{':
                derinlik += 1
            elif css[k] == '}':
                derinlik -= 1
                if derinlik == 0:
                    break
            k += 1
        i = k + 1
    return ''.join(cikti)


def _ozgulluk(secici):
    return (len(re.findall(r'#[\w-]+', secici)),
            len(re.findall(r'\.[\w-]+', secici))
            + len(re.findall(r'\[[^\]]*\]', secici))
            + len(re.findall(r'(?<!:):(?!:)[\w-]+', secici)),
            len(re.findall(r'(?:^|[\s>+~])([a-zA-Z][\w-]*)', secici)))


def _uzun(ozellik, deger):
    o, d = ozellik.strip().lower(), deger.strip()
    if o in ('border', 'border-left'):
        p = d.split()
        return {'border-left-width': p[0] if len(p) > 0 else '',
                'border-left-style': p[1] if len(p) > 1 else '',
                'border-left-color': ' '.join(p[2:]) if len(p) > 2 else ''}
    if o in ('border-left-style', 'border-left-color', 'border-left-width',
             'opacity'):
        return {o: d}
    return {}


def _eslesir(secici, siniflar):
    s = secici.strip()
    if not s or '#' in s or re.search(r'[\s>+~,]', s):
        return False
    if '::' in s or re.search(r'(?<!:):(?!:)', s):
        return False
    govde = re.sub(r'^[a-zA-Z][\w-]*', '', s)
    istenen = re.findall(r'\.([\w-]+)', govde)
    if not istenen or re.sub(r'\.[\w-]+', '', govde).strip():
        return False
    return set(istenen) <= siniflar


def _basamak_kazanani(kaynaklar, siniflar, ozellik):
    """Yükleme sırasına göre verilen CSS parçalarında kazanan bildirim."""
    bildirimler, sayac = [], 0
    for ad, css in kaynaklar:
        for m in _KURAL.finditer(_css_temizle(css)):
            for secici in m.group(1).split(','):
                if not _eslesir(secici, siniflar):
                    continue
                for parca in m.group(2).split(';'):
                    if ':' not in parca:
                        continue
                    oz, _, deg = parca.partition(':')
                    onemli = '!important' in deg
                    for uzun_ad, uzun_deg in _uzun(
                            oz, deg.replace('!important', '')).items():
                        if not uzun_deg or uzun_ad != ozellik:
                            continue
                        sayac += 1
                        bildirimler.append((onemli, _ozgulluk(secici), sayac,
                                            ad, secici.strip(),
                                            uzun_deg.strip()))
    if not bildirimler:
        return None
    return sorted(bildirimler)[-1]


def _formul_kaynaklari():
    """`/formulas` sayfasının CSS'i, GERÇEK YÜKLEME SIRASIYLA."""
    fx = _oku('hrma', 'templates', 'formulas.html')
    ici = re.search(r'<style>(.*?)</style>', fx, re.S)
    assert ici, 'formulas.html satır içi <style> bloğunu kaybetti'
    link = fx.find('href="/static/css/theme.css"')
    assert link > fx.find('</style>') >= 0, (
        'theme.css <link>i satır içi <style>ten ÖNCE alınmış — bu ölçümün '
        'yükleme sırası varsayımı bozuldu, bekçiyi güncelle')
    return [('formulas.html<style>', ici.group(1)),
            ('theme.css', _oku('hrma', 'static', 'css', 'theme.css'))]


# ===========================================================================
# OH-GT-12 — vurgusuz formül kutusu
# ===========================================================================
class TestGT12VurgusuzKutu:
    """P12bB4-12 GERİLEMİŞTİ: ayrım sayfada görünmüyordu.

    ÖLÇÜLDÜ (``a1/once.json``): eşleşen 13 bildirimin
    ``border-left-style`` kazananı ``theme.css``in ``.formula-box`` kuralı
    ve değeri ``solid`` — kesikli sol çizgi sayfada HİÇ YOKTU. Sebep satır
    içi bloktaki sıra değil, ``theme.css``in o bloktan SONRA yüklenmesiydi;
    iki kural da (0,1,0) özgüllükteydi.
    """

    KUTU_SINIFLARI = {'formula-box', 'formula-illustrative'}

    def test_kesikli_sol_cizgi_BASAMAKTAN_kazaniyor(self):
        kazanan = _basamak_kazanani(_formul_kaynaklari(), self.KUTU_SINIFLARI,
                                    'border-left-style')
        assert kazanan is not None, 'sol kenar bildirimi hiç yok'
        _, _, _, kaynak, secici, deger = kazanan
        assert deger == 'dashed', (
            'vurgusuz kutunun kesikli sol çizgisi basamakta KAYBEDİYOR: '
            'kazanan %r (%s) = %r. Ayrım yalnız opaklığa iniyor, yani tek '
            'eksen kalıyor (WCAG 1.4.1).' % (secici, kaynak, deger))

    def test_ayrim_SIRAYA_degil_OZGULLUGE_dayaniyor(self):
        """Kazanan kural, ``.formula-box``tan YÜKSEK özgüllükte olmalı.

        Sıraya dayanan bir ayrım, dosya yükleme sırası değişince (ya da
        yeni bir tema dosyası eklenince) sessizce ölür — P12bB4-12'de
        tam olarak bu oldu.
        """
        kazanan = _basamak_kazanani(_formul_kaynaklari(), self.KUTU_SINIFLARI,
                                    'border-left-style')
        _, ozgulluk, _, _, secici, _ = kazanan
        taban = _ozgulluk('.formula-box')
        assert ozgulluk > taban, (
            'kesikli çizgiyi veren kural (%r, özgüllük %s) `.formula-box` '
            'ile aynı ya da daha düşük özgüllükte (%s) — ayrım yine '
            'yükleme sırasına bağlı' % (secici, ozgulluk, taban))

    def test_opaklik_ekseni_de_duruyor(self):
        kazanan = _basamak_kazanani(_formul_kaynaklari(), self.KUTU_SINIFLARI,
                                    'opacity')
        assert kazanan is not None and float(kazanan[-1]) < 1.0, (
            'vurgusuzluğun ikinci ekseni (opaklık) kayboldu')

    def test_sinif_METIN_eklemiyor(self):
        """Ayrım biçimdir; CSS ``content`` ile çevrilemeyen metin üretmez."""
        for ad, css in _formul_kaynaklari():
            for m in _KURAL.finditer(_css_temizle(css)):
                for secici in m.group(1).split(','):
                    if 'formula-illustrative' in secici:
                        assert 'content' not in m.group(2), (
                            '%s içindeki %r kuralı `content` ile metin '
                            'üretiyor' % (ad, secici.strip()))

    def test_sablon_vurgusuz_kutulari_koruyor(self):
        fx = _oku('hrma', 'templates', 'formulas.html')
        assert len(re.findall(r'formula-box formula-illustrative', fx)) >= 5


# ===========================================================================
# OH-GT-13 — güverte sekmelerinde seçili durum
# ===========================================================================
def _islev(kaynak, imza):
    m = re.search(re.escape(imza) + r'(.*?)\n    \}', kaynak, re.S)
    assert m, '%r bulunamadı' % imza
    return m.group(1)


class TestGT13SekmeSecimi:
    """ÖLÇÜLDÜ (``a1/once.json``): ``renk_disi_eksen_sayisi`` = 0;
    ``role="tab"``, ``role="tablist"``, ``aria-selected`` hiçbiri yoktu.
    Seçili bölme SADECE renkle anlatılıyordu."""

    @pytest.fixture(scope='class')
    def dock(self):
        return _oku('hrma', 'static', 'js', 'analysis_dock.js')

    def test_serit_tablist(self, dock):
        m = re.search(r'id="ad_tabs"[^>]*', dock)
        assert m and 'role="tablist"' in m.group(0), (
            'sekme şeridi `role="tablist"` taşımıyor')

    def test_dugme_tab_rolu_ve_bagi(self, dock):
        d = _islev(dock, 'function tabButtonHtml(cat) {')
        for oznitelik in ('role="tab"', 'aria-selected=', 'aria-controls=',
                          'id="ad_tab_'):
            assert oznitelik in d, 'sekme düğmesi %r taşımıyor' % oznitelik

    def test_bolme_tabpanel(self, dock):
        assert "pane.setAttribute('role', 'tabpanel')" in dock
        assert "'aria-labelledby', 'ad_tab_' + cat" in dock

    def test_secimde_aria_selected_yaziliyor(self, dock):
        sec = _islev(dock, 'function selectCategory(cat) {')
        assert 'aria-selected' in sec, (
            'seçim değişince `aria-selected` güncellenmiyor — ekran okuyucu '
            'hangi bölmenin açık olduğunu bilemez')

    def test_secim_RENK_DISI_en_az_iki_eksen(self, dock):
        """Renk körü kullanıcı için renk tek başına bilgi değildir."""
        sec = _islev(dock, 'function selectCategory(cat) {')
        eksenler = {
            'kalınlık': bool(re.search(r'\.style\.fontWeight', sec)),
            'alt çizgi': bool(re.search(r'\.style\.borderBottomColor', sec)),
        }
        assert sum(eksenler.values()) >= 2, (
            'seçili sekme renkten bağımsız yeterli eksen taşımıyor: %s'
            % eksenler)

    def test_alt_cizgi_YERI_her_zaman_ayrilmis(self, dock):
        """Yer ayrılmazsa seçim değişince şerit zıplar."""
        d = _islev(dock, 'function tabButtonHtml(cat) {')
        assert 'border-bottom:2px solid transparent' in d, (
            'seçili alt çizginin yeri ayrılmamış (`border-bottom:none` '
            'geri gelmiş olabilir) — seçim değişince yerleşim kayar')

    def test_alt_cizgi_borderColor_KISA_yaziminin_ARDINDAN_yaziliyor(self, dock):
        """``borderColor`` alt kenarı da boyar; sıra ters olursa çizgi ölür."""
        sec = _islev(dock, 'function selectCategory(cat) {')
        assert (sec.index('.style.borderColor')
                < sec.index('.style.borderBottomColor')), (
            '`borderBottomColor`, `borderColor` kısa yazımından ÖNCE '
            'yazılıyor — seçili alt çizgi hemen ardından siliniyor')

    def test_ok_tuslariyla_gezinme(self, dock):
        assert 'function tabKeyNav(' in dock
        assert "btn.addEventListener('keydown', tabKeyNav)" in dock
        nav = dock[dock.index('function tabKeyNav('):]
        for tus in ('ArrowRight', 'ArrowLeft', 'Home', 'End'):
            assert tus in nav[:1200], '%s tuşu desteklenmiyor' % tus


# ===========================================================================
# OH-GT-14 — güvertede ham arka uç kodu
# ===========================================================================
@pytest.fixture(scope='module')
def dock_red_metni():
    """Çeviri katmanını node içinde koşturup gerçek çıktıyı okur."""
    if shutil.which('node') is None:                    # pragma: no cover
        pytest.skip('node yok — davranış ölçümü koşulamıyor')
    r = subprocess.run(
        ['node', kanit_gerekli(os.path.join(KANIT, 'dock_hata_olcum.js')),
         os.path.join(KOK, 'hrma', 'static', 'js', 'analysis_dock.js')],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, 'ölçüm betiği düştü: %s' % r.stderr[-500:]
    return json.loads(r.stdout)


class TestGT14HamKodBasilmiyor:
    """ÖLÇÜLDÜ (``a1/once.json``): ``runPanel`` reddi
    ``throw new Error(data.error || ...)`` ile kuruluyordu ve ekrana
    "HATA: incomplete_flow_input" düşüyordu. Aynı ölçümde dört ucun hata
    gövdesi canlı okundu: dördü de ``message`` taşıyor, üçü
    ``missing_fields``, ikisi ``invalid_fields``. Bilginin tamamı vardı,
    güverte hepsini atıyordu."""

    BILINEN = ('flow · incomplete_flow_input',
               'thermal · invalid_thermal_input',
               'structural · incomplete_structural_input',
               'safety · incomplete_safety_input')

    def test_cevirici_var(self, dock_red_metni):
        assert dock_red_metni.get('cevirici_var'), dock_red_metni

    def test_ham_kod_tek_basina_BASILMIYOR(self, dock_red_metni):
        for ad, v in dock_red_metni['vakalar'].items():
            assert not v['ham_kod_tek_basina'], (
                '%s: ekrana ham kod düşüyor (%r)' % (ad, v['metin']))

    @pytest.mark.parametrize('vaka', BILINEN)
    def test_bilinen_kod_insan_cumlesine_ceviriliyor(self, dock_red_metni,
                                                     vaka):
        v = dock_red_metni['vakalar'][vaka]
        kod = vaka.split(' · ')[1]
        assert kod not in v['metin'], (
            '%s: makine kodu hâlâ kullanıcıya basılıyor' % vaka)
        assert len(v['metin'].split()) >= 8, (
            '%s: metin bir cümle bile değil: %r' % (vaka, v['metin']))

    @pytest.mark.parametrize('vaka', BILINEN)
    def test_hangi_alanin_sorunlu_oldugu_YAZILIYOR(self, dock_red_metni, vaka):
        v = dock_red_metni['vakalar'][vaka]
        assert v['alan_adi_sayisi'] >= 1, (
            '%s: kullanıcı hangi alanı düzelteceğini okumuyor: %r'
            % (vaka, v['metin']))

    def test_TANINMAYAN_kod_ham_ve_ISARETLI(self, dock_red_metni):
        """Fail-closed (Doktrin 1): tanınmayan kod çevrilmez, uydurulmaz."""
        v = dock_red_metni['vakalar']['TANINMAYAN kod (fail-closed)']
        assert 'xlsx_budget_exceeded' in v['metin'], (
            'tanınmayan kod yutulmuş — kullanıcı ucun ne dediğini göremiyor')
        assert 'does not recognise' in v['metin'], (
            'tanınmayan kod, TANINMIŞ gibi basılıyor (işaret yok)')

    def test_KODSUZ_ret_de_sessiz_gecmiyor(self, dock_red_metni):
        v = dock_red_metni['vakalar']['kodsuz ret (fail-closed)']
        assert '500' in v['metin'] and len(v['metin'].split()) >= 6

    def test_uc_gerekcesi_alan_adi_yokken_YUTULMUYOR(self, dock_red_metni):
        v = dock_red_metni['vakalar']['TANINMAYAN kod (fail-closed)']
        assert 'workbook' in v['metin'], (
            'alan listesi olmayan yanıtta ucun kendi gerekçesi düşürülmüş')

    def test_kaynakta_ham_firlatma_geri_gelmemis(self):
        dock = _oku('hrma', 'static', 'js', 'analysis_dock.js')
        assert 'throw new Error(data.error ||' not in dock, (
            'ham kod fırlatma geri geldi')


# ===========================================================================
# OH-GT-15 — ayarlar penceresi punto kademesi
# ===========================================================================
class TestGT15BaslikKademesi:
    """ÖLÇÜLDÜ (``a1/once.json``): ``sectionTitle`` 13 px, ``descLine``
    13 px; ``baslik_govdeden_buyuk`` = false."""

    @pytest.fixture(scope='class')
    def panel(self):
        return _oku('hrma', 'static', 'js', 'settings_panel.js')

    def _px(self, panel, imza):
        sabitler = {a: int(b) for a, b in
                    re.findall(r'var (PX_\w+)\s*=\s*(\d+)\s*;', panel)}
        govde = _islev(panel, imza)
        m = re.search(r"font-size:'\s*\+\s*(PX_\w+)", govde)
        assert m, '%s içinde belirteçten türeyen font-size yok' % imza
        ad = m.group(1)
        if ad in sabitler:
            return ad, sabitler[ad]
        t = re.search(r'var %s\s*=\s*([^;]+);' % re.escape(ad), panel)
        assert t, '%s tanımı yok' % ad
        ifade = t.group(1)
        for s_ad, s_deg in sorted(sabitler.items(), key=lambda x: -len(x[0])):
            ifade = ifade.replace(s_ad, str(s_deg))
        return ad, int(eval(ifade, {'__builtins__': {}}, {}))

    def test_bolum_basligi_govdeden_BUYUK(self, panel):
        b_ad, b_px = self._px(panel, 'function sectionTitle(key, fallback) {')
        g_ad, g_px = self._px(panel, 'function descLine(key, fallback) {')
        assert b_px > g_px, (
            'bölüm başlığı (%s=%d px) gövde satırıyla (%s=%d px) aynı ya da '
            'daha küçük — hiyerarşi yalnız ağırlık/renk eksenine kalıyor'
            % (b_ad, b_px, g_ad, g_px))

    def test_govde_D21_tabanindan_ASAGI_inmiyor(self, panel):
        """D21 kontrast hükmü: hiçbir satır PX_TABAN'ın altında basılmaz."""
        _, g_px = self._px(panel, 'function descLine(key, fallback) {')
        sabitler = {a: int(b) for a, b in
                    re.findall(r'var (PX_\w+)\s*=\s*(\d+)\s*;', panel)}
        assert g_px >= sabitler['PX_TABAN'] >= 13

    def test_baslik_boyutu_TABANDAN_TUREVDIR(self, panel):
        """Taban büyürse kademe kendiliğinden korunmalı (tek kaynak)."""
        m = re.search(r'var PX_BOLUM_BASLIK\s*=\s*([^;]+);', panel)
        assert m, 'PX_BOLUM_BASLIK tanımı yok'
        assert 'PX_TABAN' in m.group(1), (
            'bölüm başlığı boyutu tabandan türetilmiyor, ikinci çıplak sayı '
            'yazılmış: %r' % m.group(1).strip())

    def test_UC_BASAMAKLI_kademe(self, panel):
        """gövde < bölüm başlığı < pencere başlığı.

        Bölüm başlığını `PX_TABAN + 2` yapmak kusuru kapatıyordu ama
        `PX_BASLIK` (15) ile EŞİTLİYORDU: bu kez pencere başlığı ile bölüm
        başlığı ayrışmaz olurdu. Kademe üç basamak olmalı.
        """
        sabitler = {a: int(b) for a, b in
                    re.findall(r'var (PX_\w+)\s*=\s*(\d+)\s*;', panel)}
        _, bolum = self._px(panel, 'function sectionTitle(key, fallback) {')
        _, govde = self._px(panel, 'function descLine(key, fallback) {')
        assert govde < bolum < sabitler['PX_BASLIK'], (
            'punto kademesi üç basamaklı değil: gövde %d, bölüm başlığı %d, '
            'pencere başlığı %d' % (govde, bolum, sabitler['PX_BASLIK']))

    def test_kaynakta_ciplak_piksel_yok(self, panel):
        """D23 kuralı: bu dosyada `font-size` her zaman belirteçten türer."""
        assert not re.findall(r"font-size:\s*\d+(?:\.\d+)?px", panel)


# ===========================================================================
# OH-GT-16 — giriş kartları
# ===========================================================================
class TestGT16KartlarBaglanti:
    """ÖLÇÜLDÜ (``a1/once.json``): üç kart da ``onclick``li ``<div>``di,
    ``odaklanabilir_kart`` = 0."""

    @pytest.fixture(scope='class')
    def index(self):
        s = _oku('hrma', 'templates', 'index.html')
        # Yorumlardaki `<a>`/`<div>` örnekleri sayıma girmesin.
        s = re.sub(r'/\*.*?\*/', ' ', s, flags=re.S)
        return re.sub(r'<!--.*?-->', ' ', s, flags=re.S)

    def _kartlar(self, index):
        return re.findall(r'<(\w+)\s+class="motor-card[^"]*"([^>]*)>', index)

    def test_uc_kart_duruyor(self, index):
        assert len(self._kartlar(index)) == 3

    def test_kartlar_GERCEK_baglanti(self, index):
        for etiket, oz in self._kartlar(index):
            assert etiket.lower() == 'a', (
                'kart hâlâ <%s> — klavyeyle odaklanamaz, orta tıkla yeni '
                'sekmede açılamaz' % etiket)
            assert re.search(r'\bhref="/', oz), 'kartta href yok: %r' % oz

    def test_onclick_ile_gezinme_KALMADI(self, index):
        for _, oz in self._kartlar(index):
            assert 'onclick=' not in oz, (
                'kart gezinmeyi hâlâ onclick ile yapıyor: %r' % oz)

    def test_ic_ice_baglanti_YOK(self, index):
        """``<a>`` içinde ``<a>`` geçersiz HTML'dir; tarayıcı kartı böler."""
        for m in re.finditer(r'<a\s+class="motor-card[^"]*"[^>]*>(.*?)</a>',
                             index, re.S):
            assert '<a' not in m.group(1), (
                'kart bağlantısının içinde ikinci bir <a> var')

    def test_kart_icindeki_dugme_hala_gorunuyor(self, index):
        assert len(re.findall(r'class="btn-enter"', index)) == 3

    def test_klavye_odagi_GORUNUR(self, index):
        assert re.search(r'\.motor-card:focus-visible\s*\{', index), (
            'kart odaklanabilir oldu ama odak göstergesi yok — klavye '
            'kullanıcısı nerede olduğunu göremez')

    def test_kart_blok_davraniyor(self, index):
        m = re.search(r'\.motor-card\s*\{([^}]*)\}', index)
        assert m and 'display: block' in m.group(1), (
            '<a> satır içi öğedir; `display` açıkça yazılmazsa kart '
            'yerleşimi ızgara dışında bozulur')


# ===========================================================================
# OH-GT-17 — katalogdaki iki KNSU satırı
# ===========================================================================
class TestGT17KnsuAyirtEdilebilir:
    """ÖLÇÜLDÜ (``a1/once.json``): iki satırın ``burn_rate_a``,
    ``burn_rate_n``, ``c_star``, ``gamma``, ``flame_temperature``,
    ``molecular_weight`` alanları BİREBİR aynı; tek gerçek fark yoğunluk
    (1889 ⟷ 1785, +%5,83). Adlardan ayırt edilemiyordu: 1889'luk satır
    yalnız "65/35" diyordu, 1785'lik satır "65/35" bile demiyordu."""

    @pytest.fixture(scope='class')
    def katalog(self):
        from hrma.data.propellants_db import PROPELLANTS
        return PROPELLANTS

    def test_yogunluk_farki_GERCEK(self, katalog):
        a, b = katalog['sugar']['density'], katalog['knsu']['density']
        assert a == pytest.approx(1785) and b == pytest.approx(1889)
        assert abs(100.0 * (b - a) / a - 5.83) < 0.02

    def test_iki_ad_da_BILESIMI_soyluyor(self, katalog):
        for k in ('knsu', 'sugar'):
            assert '65/35' in katalog[k]['name'], (
                '%r adı bileşimi söylemiyor: %r' % (k, katalog[k]['name']))

    def test_iki_ad_da_YOGUNLUK_TABANINI_soyluyor(self, katalog):
        beklenen = {'knsu': 'theoretical maximum', 'sugar': 'cast bulk'}
        for k, imza in beklenen.items():
            assert imza in katalog[k]['name'].lower(), (
                '%r adı yoğunluk tabanını söylemiyor: %r — seçim listesinde '
                'iki satır ayırt edilemez' % (k, katalog[k]['name']))

    def test_adlar_birbirinden_FARKLI(self, katalog):
        assert katalog['knsu']['name'] != katalog['sugar']['name']

    def test_ada_SAYI_yazilmamis(self, katalog):
        """Tek kaynak ``density`` alanıdır; ad onu kopyalamaz."""
        for k in ('knsu', 'sugar'):
            ad = katalog[k]['name']
            assert not re.search(r'\b1[78]\d\d\b', ad), (
                '%r adına yoğunluk sayısı yazılmış (ikinci kaynak): %r'
                % (k, ad))

    def test_motor_adi_KATALOGDAN_turetiliyor(self):
        """Aynı ad iki dosyada yazılmaz — motor kataloğu okur."""
        motor = _oku('hrma', 'engines', 'solid_rocket_engine.py')
        n = len(re.findall(
            r"name=_PROPELLANT_CATALOG\['(?:knsu|sugar)'\]\['name'\]", motor))
        assert n == 2, (
            'iki KNSU satırının adı motorda hâlâ elle yazılı (%d/2 '
            'türetilmiş) — katalogla ayrışabilir' % n)

    def test_motorun_bastigi_ad_KATALOGLA_ayni(self, katalog):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        for anahtar in ('knsu', 'sugar'):
            e = SolidRocketEngine(propellant_type=anahtar)
            assert e.propellant_name == katalog[anahtar]['name'], (
                '%s: motor %r, katalog %r'
                % (anahtar, e.propellant_name, katalog[anahtar]['name']))

    def test_ad_KENDI_kaydina_coz(self, katalog):
        """Ad değişti; çözücü iki satırı hâlâ doğru ayırmalı (P2B1-10)."""
        from hrma.engines.solid_rocket_engine import _catalog_key_from_text
        for anahtar in ('knsu', 'sugar'):
            assert _catalog_key_from_text(katalog[anahtar]['name']) == anahtar


# ===========================================================================
# OH-GT-18 — yayımlanmamış sürümün tarihi
# ===========================================================================
class TestGT18YayimlanmamisSurum:
    """ÖLÇÜLDÜ (``a1/once.json``): en üst sürüm 2.6.27 başlıkta
    "2026-08-15" basıyordu; aynı kaydın başlığı ve gövdesi
    "in development / has NOT been published yet" diyor."""

    @pytest.fixture(scope='class')
    def changelog(self):
        return json.loads(_oku('hrma', 'data', 'changelog.json'))

    @pytest.fixture(scope='class')
    def notlar(self):
        return _oku('hrma', 'static', 'js', 'release_notes.js')

    def test_gelistirmedeki_surum_TARIH_TASIMIYOR(self, changelog):
        for v in changelog['versions']:
            gelisiyor = ('in development' in (v.get('title') or '')
                         or v.get('unreleased') is True)
            if gelisiyor:
                assert not v.get('date'), (
                    '%s hâlâ yayımlanmamışken yayın tarihi taşıyor: %r'
                    % (v['version'], v.get('date')))

    def test_tarihsiz_surum_ISARETLI(self, changelog):
        """Tarih yokluğu sessiz olamaz: durum ADIYLA yazılır."""
        for v in changelog['versions']:
            if not v.get('date'):
                assert v.get('unreleased') is True, (
                    '%s tarihsiz ama `unreleased` işareti yok — okuyucu '
                    'tarihin neden olmadığını bilemez' % v['version'])

    def test_yayimlanmis_surumler_tarihini_KORUYOR(self, changelog):
        yayimli = [v for v in changelog['versions']
                   if v.get('unreleased') is not True]
        assert len(yayimli) >= 14
        for v in yayimli:
            assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', v.get('date') or ''), (
                '%s yayımlanmış ama tarihi yok/biçimsiz' % v['version'])

    def test_JS_unreleased_ISARETINI_okuyor(self, notlar):
        blok = _islev(notlar, 'function buildVersionBlock(v) {')
        assert 'v.unreleased === true' in blok, (
            'sürüm notları penceresi `unreleased` işaretini görmüyor')

    def test_JS_tarihsiz_surumu_SESSIZ_gecmiyor(self, notlar):
        """Fail-closed: ne yayımlanmamış ne tarihli kayıt boş geçilmez."""
        blok = _islev(notlar, 'function buildVersionBlock(v) {')
        assert 'release.status.noDate' in blok, (
            'tarihi olmayan ve `unreleased` da olmayan kayıtta başlıkta '
            'sessiz boşluk kalıyor')

    def test_JS_SAHTE_tarih_uretmiyor(self, notlar):
        blok = _islev(notlar, 'function buildVersionBlock(v) {')
        assert not re.search(r'new Date\(|toISOString|Date\.now', blok), (
            'sürüm başlığı tarihi çalışma anından üretiyor — yayın tarihi '
            'uydurulamaz')
