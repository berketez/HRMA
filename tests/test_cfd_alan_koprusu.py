"""CFD alan köprüsü — ÇAPRAZ SÖZLEŞME bekçileri (parti 30, A3).

NEDEN VAR
---------
Parti 28'de panel ile uç arasındaki sözleşme SÜRÜKLENMİŞ, süit yeşil
kaldığı için kimse görmemişti: her iki taraf da kendi içinde tutarlıydı,
aralarındaki eşleşmeyi ölçen bir bekçi yoktu. Alan köprüsü ÜÇ tarafı
birbirine bağlıyor —

    hrma/app.py                 (uç: 'field' sözlüğündeki gerçek anahtarlar)
    motor_viz3d.js              (3B sahne: CFD_METRICS / CFD_REASONS tabloları)
    panels/cfd_panel.js         (2B panel: seçici + 3B köprüsü)
    motor_viz_deck.js           (güverte: yüklü alanın denetimleri)

— dolayısıyla sürüklenme ihtimali dört kat. Buradaki bekçiler tarafların
kendi içindeki tutarlılığı değil, ARALARINDAKİ KÜME EŞİTLİĞİNİ ölçer.

NE KİLİTLENİR
-------------
  a) Panelin ve güvertenin kullandığı metrik KİMLİK kümesi ==
     motor_viz3d.js CFD_METRICS tablosundaki kimlikler.
  b) Panelin ve güvertenin ELE ALDIĞI red kod kümesi == motor_viz3d.js'in
     ÜRETEBİLDİĞİ red kod kümesi (kaynaktan ayrıştırılır; testte sabit
     liste YAZILMAZ, sözleşme metni de kaynak sayılmaz).
  c) Metrik payloadKey'leri == ucun GERÇEK yanıtındaki hücre-ızgarası
     anahtarları (geometri çifti dışında). Uca dördüncü bir büyüklük
     eklenip istemciye bağlanmazsa bu bekçi kırmızı döner.
  d) cfd_panel.js'de Plotly renk skalası ADI (string literal) YOK —
     renkler paylaşılan durak tablosundan gelir, iki tanım kalmaz.
  e) cfd_panel.js yüklenen HER şablonda motor_viz3d.js daha ÖNCE yüklenir
     (aynı kural güverte için de ölçülür).

ÖLÇÜM YÖNTEMİ
-------------
Tablolar ve listeler dosyaların KENDİ bildirimlerinden çıkarılıp node ile
değerlendirilir (Python kopyası yok). Uç anahtarları CANLI ``/api/cfd/nozzle``
yanıtından okunur. Her bekçi SAF bir denetim fonksiyonu üstünden çalışır;
mutasyon aynı fonksiyona BOZULMUŞ girdi vererek ölçülür — böylece ısırık
geliştirme anında bir kez değil, HER koşumda yeniden kanıtlanır ve disk
üstündeki kaynak dosyalara hiç dokunulmaz.

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_cfd_alan_koprusu.py -q
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_cfd_endpoint import _sessiz, govde

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'

VIZ3D_JS = STATIC_JS / 'motor_viz3d.js'
PANEL_JS = STATIC_JS / 'panels' / 'cfd_panel.js'
DECK_JS = STATIC_JS / 'motor_viz_deck.js'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Alan bloğundaki hücre ızgaralarından GEOMETRİ olanlar. Bunlar büyüklük
#: değil koordinattır; 3B sahne ikisini de ADIYLA şart koşuyor
#: (cfdFieldBlockDefect: field.z_m / field.r_m). Adları uçta değişirse
#: test_geometri_anahtarlari_sahnede_adiyla_sart bekçisi kırmızı döner.
GEOMETRI_ANAHTARLARI = ('z_m', 'r_m')

#: cfd_panel.js'de yasak olan Plotly renk skalası ADLARI. Liste kapalı
#: değil: kaynakta Plotly'nin BİLİNEN skala adlarından herhangi biri
#: string literal olarak geçerse bekçi konuşur. (Vendor Plotly 1.58.5'in
#: yayımladığı adların tamamı — ölçüldü: PLOTLY_SCALES anahtarları.)
PLOTLY_SKALA_ADLARI = (
    'Greys', 'YlGnBu', 'Greens', 'YlOrRd', 'Bluered', 'RdBu', 'Reds',
    'Blues', 'Picnic', 'Rainbow', 'Portland', 'Jet', 'Hot', 'Blackbody',
    'Earth', 'Electric', 'Viridis', 'Cividis',
)

#: Şablonların yüklediği betiklerin sırası ölçülürken kullanılan yollar.
PANEL_SRC = '/static/js/panels/cfd_panel.js'
VIZ3D_SRC = '/static/js/motor_viz3d.js'
DECK_SRC = '/static/js/motor_viz_deck.js'


# ---------------------------------------------------------------------------
# Kaynak çıkarımı — bildirimler dosyaların KENDİSİNDEN, Python kopyası yok
# ---------------------------------------------------------------------------

def _oku(path):
    return path.read_text(encoding='utf-8')


def bildirim(path, ad, anahtar_kelime='var'):
    """``var/const AD = ...;`` bildirimini kaynaktan AYNEN çıkarır.

    ``[^;]+`` biçimi bu dosyaların yazım kuralına dayanır: bu bildirimlerin
    literalleri ';' içermez (A2'nin tests/test_viz3d_cfd_alan.py bekçisi
    aynı varsayımla çalışıyor).
    """
    m = re.search(r'%s %s = [^;]+;' % (anahtar_kelime, re.escape(ad)),
                  _oku(path))
    assert m, '%s içinde %s bildirimi bulunamadı' % (path.name, ad)
    return m.group(0)


def js_degeri(prelude, ifade):
    """Çıkarılan bildirimleri node'da değerlendirip JSON olarak döner."""
    betik = prelude + '\nprocess.stdout.write(JSON.stringify(%s));\n' % ifade
    p = subprocess.run([NODE, '-e', betik], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr[:1500]
    return json.loads(p.stdout)


def strip_js_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur).

    tests/test_cfd_panel.py'deki aynı adlı yardımcının davranışı: yorum
    metni denetimi kirletmemeli — panelin açıklama satırları renk skalası
    adını bilerek ANIYOR ("Plotly skala ADI ('Viridis' gibi) KULLANILMAZ").
    """
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


# ---------------------------------------------------------------------------
# SAF DENETİM FONKSİYONLARI — bekçi de mutasyon da AYNI fonksiyonu çağırır
# ---------------------------------------------------------------------------

def kume_esitligi(sol, sag, sol_ad, sag_ad):
    """İki kümenin eşitliğini ölçer; eşit değilse AssertionError atar."""
    sol, sag = set(sol), set(sag)
    fazla = sorted(sol - sag)
    eksik = sorted(sag - sol)
    assert not fazla and not eksik, (
        '%s ile %s kümeleri ayrışmış — %s\'de fazla: %s / eksik: %s'
        % (sol_ad, sag_ad, sol_ad, fazla, eksik))


def payload_eslemesi_ayni(panel, sahne):
    """id -> payloadKey eşlemeleri birebir mi? Değilse AssertionError."""
    assert panel == sahne, (
        'aynı kimlik iki tarafta FARKLI yük anahtarına bakıyor: '
        'panel=%r sahne=%r' % (panel, sahne))


def metrik_izgara_anahtarlari(field):
    """Alan bloğundaki BÜYÜKLÜK ızgaralarının anahtarları (ölçülerek).

    Kural sabit liste değil YAPIDIR: değeri ``shape`` ile birebir aynı
    boyutta, sayısal, iç içe liste olan her anahtar bir hücre ızgarasıdır;
    bunlardan geometri çifti (z_m / r_m) düşülür. Uca dördüncü bir
    büyüklük eklenirse burada kendiliğinden görünür.
    """
    ni, nj = field['shape']
    out = set()
    for k, v in field.items():
        if not isinstance(v, list) or len(v) != ni:
            continue
        if not v or not isinstance(v[0], list) or len(v[0]) != nj:
            continue
        if not all(isinstance(x, (int, float)) for x in v[0]):
            continue
        out.add(k)
    return out - set(GEOMETRI_ANAHTARLARI)


def renk_skalasi_adi_gecenler(kaynak):
    """Kaynakta STRING LİTERAL olarak geçen Plotly skala adları."""
    temiz = strip_js_comments(kaynak)
    bulunan = set()
    for ad in PLOTLY_SKALA_ADLARI:
        if re.search(r"""['"]%s['"]""" % re.escape(ad), temiz):
            bulunan.add(ad)
    return bulunan


def yukleme_sirasi(sablon_metni, once_src, sonra_src):
    """(once_ofset, sonra_ofset) — betik yoksa None döner."""
    def ofset(src):
        m = re.search(r'<script[^>]+src="%s"' % re.escape(src), sablon_metni)
        return m.start() if m else None
    return ofset(once_src), ofset(sonra_src)


def sira_dogru_mu(sablon_metni, once_src, sonra_src):
    """`sonra_src` yükleniyorsa `once_src` ondan ÖNCE yüklenmeli."""
    once, sonra = yukleme_sirasi(sablon_metni, once_src, sonra_src)
    if sonra is None:
        return True                     # bu şablon o betiği hiç yüklemiyor
    if once is None:
        return False                    # bağımlılık hiç yüklenmemiş
    return once < sonra


# ---------------------------------------------------------------------------
# Fikstürler — GERÇEK kaynaklar ve GERÇEK uç yanıtı
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def viz3d_metrics():
    return js_degeri(bildirim(VIZ3D_JS, 'CFD_METRICS'), 'CFD_METRICS')


@pytest.fixture(scope='module')
def viz3d_colorscales():
    return js_degeri(bildirim(VIZ3D_JS, 'CFD_COLORSCALES'), 'CFD_COLORSCALES')


@pytest.fixture(scope='module')
def viz3d_reason_keys():
    """Sahnenin RED TABLOSUNDAKİ kodlar (yayımlanmış küme)."""
    return set(js_degeri(bildirim(VIZ3D_JS, 'CFD_REASONS'),
                         'Object.keys(CFD_REASONS)'))


@pytest.fixture(scope='module')
def viz3d_uretilen_kodlar():
    """Kaynakta GERÇEKTEN üretilen red kodları (çağrı yerlerinden)."""
    temiz = strip_js_comments(_oku(VIZ3D_JS))
    kodlar = set(re.findall(r"cfdReason\(\s*'(\w+)'", temiz))
    kodlar |= set(re.findall(r"code:\s*'(\w+)'", temiz))
    assert kodlar, 'motor_viz3d.js içinde hiç red kodu üretimi bulunamadı'
    return kodlar


@pytest.fixture(scope='module')
def panel_metrics():
    prelude = (bildirim(PANEL_JS, 'PA_PER_BAR', 'const') + '\n'
               + bildirim(PANEL_JS, 'FIELD_METRICS', 'const'))
    return js_degeri(prelude, 'FIELD_METRICS')


@pytest.fixture(scope='module')
def panel_reason_codes():
    return js_degeri(bildirim(PANEL_JS, 'VIZ3D_REASON_CODES', 'const'),
                     'VIZ3D_REASON_CODES')


@pytest.fixture(scope='module')
def deck_symbols():
    return js_degeri(bildirim(DECK_JS, 'CFD_METRIC_SYMBOLS'),
                     'CFD_METRIC_SYMBOLS')


@pytest.fixture(scope='module')
def deck_reason_codes():
    return js_degeri(bildirim(DECK_JS, 'CFD_REASON_CODES'), 'CFD_REASON_CODES')


@pytest.fixture(scope='module')
def uc_field():
    """CANLI ``/api/cfd/nozzle`` yanıtının alan bloğu (~1,5 s)."""
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = _sessiz(c.post, '/api/cfd/nozzle', json=govde())
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    field = r.get_json()['cfd']['field']
    assert isinstance(field, dict) and 'shape' in field, 'alan bloğu gelmedi'
    return field


@pytest.fixture(scope='module')
def sablonlar():
    return {p.name: _oku(p) for p in sorted(TEMPLATES.glob('*.html'))}


# ---------------------------------------------------------------------------
# a) METRİK KİMLİK KÜMESİ — panel / güverte / 3B sahne
# ---------------------------------------------------------------------------
class TestMetrikKimlikleri:
    def test_panel_kimlikleri_sahneyle_ayni(self, panel_metrics, viz3d_metrics):
        kume_esitligi([m['id'] for m in panel_metrics],
                      [m['id'] for m in viz3d_metrics],
                      'cfd_panel.js FIELD_METRICS', 'motor_viz3d.js CFD_METRICS')

    def test_guverte_sembolleri_sahneyle_ayni(self, deck_symbols, viz3d_metrics):
        """Güvertede sembolü olmayan metrik düğmesiz kalırdı (sessiz kayıp)."""
        kume_esitligi(deck_symbols.keys(), [m['id'] for m in viz3d_metrics],
                      'motor_viz_deck.js CFD_METRIC_SYMBOLS',
                      'motor_viz3d.js CFD_METRICS')

    def test_uc_buyukluk_bekleniyor(self, viz3d_metrics):
        """Parti 30 kapsamı: Mach + statik basınç + statik sıcaklık."""
        assert len(viz3d_metrics) == 3, (
            'metrik sayısı değişmiş: %d' % len(viz3d_metrics))

    def test_her_metrigin_renk_skalasi_var(self, viz3d_metrics,
                                           viz3d_colorscales):
        kume_esitligi(viz3d_colorscales.keys(),
                      [m['id'] for m in viz3d_metrics],
                      'CFD_COLORSCALES', 'CFD_METRICS')
        for id_, duraklar in viz3d_colorscales.items():
            assert len(duraklar) >= 2, '%s skalası tek duraklı' % id_
            assert duraklar[0][0] == 0 and duraklar[-1][0] == 1, (
                '%s skalası 0..1 aralığını kapatmıyor' % id_)

    # --- MUTASYON: sahne tablosuna sahte bir metrik girerse ---------------
    def test_mutasyon_sahte_metrik_kirmizi(self, panel_metrics, viz3d_metrics):
        bozuk = [m['id'] for m in viz3d_metrics] + ['density']
        with pytest.raises(AssertionError) as e:
            kume_esitligi([m['id'] for m in panel_metrics], bozuk,
                          'panel', 'sahne(bozuk)')
        assert 'density' in str(e.value), (
            'bekçi eksik kimliği ADIYLA söylemiyor')

    def test_mutasyon_eksik_metrik_kirmizi(self, panel_metrics, viz3d_metrics):
        """Panelden sıcaklık düşerse (eski hâl) bekçi konuşmalı."""
        bozuk = [m['id'] for m in panel_metrics if m['id'] != 'temperature']
        with pytest.raises(AssertionError) as e:
            kume_esitligi(bozuk, [m['id'] for m in viz3d_metrics],
                          'panel(bozuk)', 'sahne')
        assert 'temperature' in str(e.value)

    def test_mutasyon_guverte_sembolu_dusunce_kirmizi(self, deck_symbols,
                                                      viz3d_metrics):
        bozuk = {k: v for k, v in deck_symbols.items() if k != 'temperature'}
        with pytest.raises(AssertionError):
            kume_esitligi(bozuk.keys(), [m['id'] for m in viz3d_metrics],
                          'güverte(bozuk)', 'sahne')


# ---------------------------------------------------------------------------
# b) RED KODU KÜMESİ — panel / güverte / 3B sahne
# ---------------------------------------------------------------------------
class TestRedKodlari:
    def test_sahne_yalniz_tablodaki_kodlari_uretiyor(self, viz3d_reason_keys,
                                                     viz3d_uretilen_kodlar):
        """Tabloda olmayan bir kod üretilse sahne çalışma anında çökerdi
        (CFD_REASONS[code] tanımsız olurdu) — kod ölçülür, varsayılmaz."""
        fazla = sorted(viz3d_uretilen_kodlar - viz3d_reason_keys)
        assert not fazla, (
            'sahne red tablosunda OLMAYAN kod üretiyor: %s' % fazla)

    def test_tablodaki_her_kod_gercekten_uretiliyor(self, viz3d_reason_keys,
                                                    viz3d_uretilen_kodlar):
        """Ölü kod koruması: yayımlanan her red kodunun bir çağrı yeri var."""
        olu = sorted(viz3d_reason_keys - viz3d_uretilen_kodlar)
        assert not olu, ('red tablosunda üretilmeyen kod var: %s' % olu)

    def test_panel_kod_kumesi_sahneyle_ayni(self, panel_reason_codes,
                                            viz3d_reason_keys):
        kume_esitligi(panel_reason_codes, viz3d_reason_keys,
                      'cfd_panel.js VIZ3D_REASON_CODES',
                      'motor_viz3d.js CFD_REASONS')

    def test_guverte_kod_kumesi_sahneyle_ayni(self, deck_reason_codes,
                                              viz3d_reason_keys):
        kume_esitligi(deck_reason_codes, viz3d_reason_keys,
                      'motor_viz_deck.js CFD_REASON_CODES',
                      'motor_viz3d.js CFD_REASONS')

    def test_panel_ve_guverte_ayni_kumeyi_tutuyor(self, panel_reason_codes,
                                                  deck_reason_codes):
        kume_esitligi(panel_reason_codes, deck_reason_codes,
                      'panel', 'güverte')

    def test_bilinmeyen_kod_adiyla_beyan_ediliyor(self, panel_reason_codes):
        """Tanınmayan kod gelirse panel bunu SESSİZCE yutmamalı: kaynakta
        listeye bakan bir dal ve 'unknownCode' beyanı bulunmalı."""
        temiz = strip_js_comments(_oku(PANEL_JS))
        assert 'VIZ3D_REASON_CODES.indexOf(kod) < 0' in temiz, (
            'panel bilinmeyen red kodunu denetlemiyor')
        assert 'panel.cfd.viz3dUnknownCode' in temiz, (
            'panel bilinmeyen kodu adıyla beyan etmiyor')
        temizD = strip_js_comments(_oku(DECK_JS))
        assert 'CFD_REASON_CODES.indexOf(kod) < 0' in temizD, (
            'güverte bilinmeyen red kodunu denetlemiyor')

    def test_mesaj_metni_sahneden_geliyor(self):
        """Panel/güverte red MESAJINI kendi yazmaz: sahnenin reason.key +
        reason.fallback çiftini kullanır (mesajın ikinci tanımı olmaz)."""
        for path in (PANEL_JS, DECK_JS):
            temiz = strip_js_comments(_oku(path))
            assert 'reason.key' in temiz and 'reason.fallback' in temiz, (
                '%s red metnini sahnenin anahtar/yedek çiftinden almıyor'
                % path.name)
            yerel = re.findall(r"T\(\s*'viz3d\.cfd\.err\.", temiz)
            assert not yerel, (
                '%s sahne hata anahtarını KENDİ yazıyor — mesaj ikiye ayrılır'
                % path.name)

    # --- MUTASYON --------------------------------------------------------
    def test_mutasyon_sahte_red_kodu_kirmizi(self, panel_reason_codes,
                                             viz3d_reason_keys):
        bozuk = set(viz3d_reason_keys) | {'webgl_lost'}
        with pytest.raises(AssertionError) as e:
            kume_esitligi(panel_reason_codes, bozuk, 'panel', 'sahne(bozuk)')
        assert 'webgl_lost' in str(e.value)

    def test_mutasyon_panelden_kod_dusunce_kirmizi(self, panel_reason_codes,
                                                   viz3d_reason_keys):
        bozuk = [k for k in panel_reason_codes if k != 'contour_mismatch']
        with pytest.raises(AssertionError) as e:
            kume_esitligi(bozuk, viz3d_reason_keys, 'panel(bozuk)', 'sahne')
        assert 'contour_mismatch' in str(e.value)


# ---------------------------------------------------------------------------
# c) YÜK ANAHTARLARI — istemci tabloları ile ucun GERÇEK yanıtı
# ---------------------------------------------------------------------------
class TestYukAnahtarlari:
    def test_sahne_payload_anahtarlari_ucta_var(self, viz3d_metrics, uc_field):
        eksik = [m['payloadKey'] for m in viz3d_metrics
                 if m['payloadKey'] not in uc_field]
        assert not eksik, ('sahne ucta OLMAYAN anahtar bekliyor: %s' % eksik)

    def test_panel_payload_anahtarlari_sahneyle_ayni(self, panel_metrics,
                                                     viz3d_metrics):
        payload_eslemesi_ayni(
            {m['id']: m['payloadKey'] for m in panel_metrics},
            {m['id']: m['payloadKey'] for m in viz3d_metrics})

    def test_ucun_butun_izgaralari_istemciye_bagli(self, uc_field,
                                                   viz3d_metrics):
        """Ucun yayımladığı her BÜYÜKLÜK ızgarasının istemcide karşılığı
        olmalı. Uca dördüncü bir alan eklenip bağlanmazsa (parti 28'in
        sürüklenme deseni) burası kırmızı döner."""
        kume_esitligi(metrik_izgara_anahtarlari(uc_field),
                      [m['payloadKey'] for m in viz3d_metrics],
                      'uç field ızgaraları', 'CFD_METRICS payloadKey')

    def test_geometri_anahtarlari_sahnede_adiyla_sart(self, uc_field):
        """z_m / r_m koordinat çiftidir, büyüklük değil: sahne ikisini de
        ADIYLA şart koşuyor. Uçta adları değişirse burası konuşur."""
        temiz = strip_js_comments(_oku(VIZ3D_JS))
        for ad in GEOMETRI_ANAHTARLARI:
            assert ad in uc_field, 'uç %s ızgarasını yayımlamıyor' % ad
            assert 'field.%s' % ad in temiz, (
                'motor_viz3d.js %s koordinatını adıyla okumuyor' % ad)

    def test_sicaklik_gercekten_geliyor(self, uc_field):
        """Parti 30'un üçüncü büyüklüğü CANLI yanıtta ölçülür (rapora
        değil koda/veriye güven)."""
        t = uc_field.get('temperature_K')
        ni, nj = uc_field['shape']
        assert isinstance(t, list) and len(t) == ni and len(t[0]) == nj, (
            'temperature_K ızgarası alan bloğunun şekliyle uyuşmuyor')
        duz = [v for row in t for v in row]
        assert all(isinstance(v, (int, float)) and v == v for v in duz)
        assert min(duz) > 0, 'statik sıcaklıkta pozitif olmayan hücre var'

    # --- MUTASYON --------------------------------------------------------
    def test_mutasyon_uca_baglanmamis_dorduncu_alan_kirmizi(self, uc_field,
                                                            viz3d_metrics):
        ni, nj = uc_field['shape']
        bozuk = dict(uc_field)
        bozuk['density_kg_m3'] = [[1.0] * nj for _ in range(ni)]
        with pytest.raises(AssertionError) as e:
            kume_esitligi(metrik_izgara_anahtarlari(bozuk),
                          [m['payloadKey'] for m in viz3d_metrics],
                          'uç(bozuk)', 'CFD_METRICS')
        assert 'density_kg_m3' in str(e.value)

    def test_mutasyon_ucta_sicaklik_yokken_kirmizi(self, uc_field,
                                                   viz3d_metrics):
        bozuk = {k: v for k, v in uc_field.items() if k != 'temperature_K'}
        with pytest.raises(AssertionError) as e:
            kume_esitligi(metrik_izgara_anahtarlari(bozuk),
                          [m['payloadKey'] for m in viz3d_metrics],
                          'uç(bozuk)', 'CFD_METRICS')
        assert 'temperature_K' in str(e.value)

    def test_mutasyon_yanlis_payload_anahtari_kirmizi(self, panel_metrics,
                                                      viz3d_metrics):
        """Panel aynı kimliğe FARKLI yük anahtarı bağlarsa (klasik birim/ad
        kayması) aynı denetim fonksiyonu kırmızı dönmeli."""
        bozuk = {m['id']: ('temperature_C' if m['id'] == 'temperature'
                           else m['payloadKey']) for m in panel_metrics}
        sahne = {m['id']: m['payloadKey'] for m in viz3d_metrics}
        with pytest.raises(AssertionError) as e:
            payload_eslemesi_ayni(bozuk, sahne)
        assert 'temperature_C' in str(e.value)


# ---------------------------------------------------------------------------
# d) RENK SKALASI — panelde Plotly ADI kalmadı, tablo tek kaynak
# ---------------------------------------------------------------------------
class TestRenkSkalasiTekKaynak:
    def test_panelde_plotly_skala_adi_yok(self):
        bulunan = renk_skalasi_adi_gecenler(_oku(PANEL_JS))
        assert not bulunan, (
            'cfd_panel.js hâlâ Plotly skala ADI kullanıyor: %s — 2B ve 3B '
            'aynı büyüklüğe farklı renk verir' % sorted(bulunan))

    def test_panel_skalayi_paylasilan_tablodan_aliyor(self):
        temiz = strip_js_comments(_oku(PANEL_JS))
        assert 'MotorViz3D.CFD_COLORSCALES' in temiz, (
            'panel paylaşılan durak tablosunu okumuyor')
        assert 'metricColorscale' in temiz

    def test_panelde_yedek_durak_tablosu_yok(self):
        """Yedek tablo = ikinci tanım = sürüklenme. Panelde hex durak
        dizisi literali bulunmamalı (grafik renkleri tek tek hex'tir,
        [sayı, '#hex'] ÇİFTİ yoktur)."""
        temiz = strip_js_comments(_oku(PANEL_JS))
        duraklar = re.findall(r"\[\s*[01](?:\.\d+)?\s*,\s*'#[0-9a-fA-F]{6}'\s*\]",
                              temiz)
        assert not duraklar, (
            'panelde renk durağı literali var (yedek tablo yazılmış): %s'
            % duraklar[:4])

    # --- MUTASYON --------------------------------------------------------
    def test_mutasyon_skala_adi_geri_gelirse_kirmizi(self):
        bozuk = _oku(PANEL_JS).replace(
            "const WALL_COLOR = ",
            "const MACH_COLORSCALE = 'Viridis';\n    const WALL_COLOR = ")
        bulunan = renk_skalasi_adi_gecenler(bozuk)
        assert 'Viridis' in bulunan, (
            'bekçi geri gelen skala adını görmüyor — kör')

    def test_mutasyon_yorum_icindeki_ad_kirmizi_yapmaz(self):
        """Ters yön: yorumda geçen ad SAHTE ALARM üretmemeli (panelin kendi
        açıklaması adı bilerek anıyor). Bu ölçüm bekçinin körlüğü değil,
        kapsamının doğruluğudur."""
        bozuk = _oku(PANEL_JS) + "\n// not: Portland artik kullanilmiyor\n"
        assert not renk_skalasi_adi_gecenler(bozuk)


# ---------------------------------------------------------------------------
# e) YÜKLEME SIRASI — motor_viz3d.js her zaman ÖNCE
# ---------------------------------------------------------------------------
class TestYuklemeSirasi:
    def test_panel_yuklenen_sablonlar_olculdu(self, sablonlar):
        panelli = [ad for ad, s in sablonlar.items() if PANEL_SRC in s]
        assert panelli, 'cfd_panel.js hiçbir şablonda yüklenmiyor'
        assert set(panelli) == {'advanced.html', 'liquid.html', 'solid.html'}, (
            'panelin yüklendiği şablon kümesi değişmiş: %s' % sorted(panelli))

    def test_her_panelli_sablonda_sahne_once(self, sablonlar):
        for ad, s in sablonlar.items():
            if PANEL_SRC not in s:
                continue
            once, sonra = yukleme_sirasi(s, VIZ3D_SRC, PANEL_SRC)
            assert once is not None, (
                '%s cfd_panel.js yüklüyor ama motor_viz3d.js yüklemiyor — '
                'renk tablosu ve 3B köprüsü ölü doğar' % ad)
            assert once < sonra, (
                '%s içinde motor_viz3d.js panelden SONRA yükleniyor '
                '(%d > %d)' % (ad, once, sonra))

    def test_her_guverteli_sablonda_sahne_once(self, sablonlar):
        guverteli = [ad for ad, s in sablonlar.items() if DECK_SRC in s]
        assert guverteli, 'motor_viz_deck.js hiçbir şablonda yüklenmiyor'
        for ad in guverteli:
            assert sira_dogru_mu(sablonlar[ad], VIZ3D_SRC, DECK_SRC), (
                '%s içinde motor_viz3d.js güverteden sonra yükleniyor' % ad)

    def test_panelde_yukleme_sirasi_beyani_var(self):
        """Kaynak, tablonun yokluğunda ne olacağını YAZIYOR olmalı (sessiz
        yanlış renk yerine beyan)."""
        temiz = strip_js_comments(_oku(PANEL_JS))
        assert 'panel.cfd.colorSourceMissing' in temiz

    # --- MUTASYON --------------------------------------------------------
    def test_mutasyon_sira_ters_cevrilirse_kirmizi(self, sablonlar):
        s = sablonlar['advanced.html']
        satir = '<script src="%s"></script>' % VIZ3D_SRC
        assert satir in s, 'şablon betik satırı biçimi değişmiş'
        # Sahne betiği sökülüp panelden SONRAYA taşınır
        bozuk = s.replace(satir, '', 1).replace(
            '<script src="%s"></script>' % PANEL_SRC,
            '<script src="%s"></script>\n%s' % (PANEL_SRC, satir), 1)
        assert not sira_dogru_mu(bozuk, VIZ3D_SRC, PANEL_SRC), (
            'bekçi ters sırayı görmüyor — kör')

    def test_mutasyon_sahne_hic_yuklenmezse_kirmizi(self, sablonlar):
        bozuk = sablonlar['solid.html'].replace(
            '<script src="%s"></script>' % VIZ3D_SRC, '', 1)
        assert not sira_dogru_mu(bozuk, VIZ3D_SRC, PANEL_SRC), (
            'bağımlılık hiç yüklenmediğinde bekçi susuyor')


# ---------------------------------------------------------------------------
# f) GÜVERTE DAVRANIŞI — node içinde gerçek dosya, taklit DOM + taklit sahne
# ---------------------------------------------------------------------------
#: Güverte gerçek WebGL sahnesi ister; node'da kurulamaz. Bu yüzden sahne
#: TAKLİT edilir ama METRİK TABLOSU GERÇEKTİR (motor_viz3d.js kaynağından
#: aynen enjekte edilir) ve dönüş sözlükleri sözleşmedeki biçimdedir.
#: Sahtenin sözleşmeden kaymadığını yukarıdaki küme bekçileri denetler.
DECK_HARNESS = r"""
'use strict';
const fs = require('fs');
const senaryo = JSON.parse(process.argv[3]);
/*VIZ3D_TABLES*/

const nodes = {};
function makeNode(id) {
    const n = {
        id: id, innerHTML: '', textContent: '', title: '', value: '',
        disabled: false, style: {}, attrs: {}, classes: {}, onclick: null,
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { return c; },
        querySelector() { return null; },
        addEventListener() {},
    };
    n.classList = {
        toggle(c, on) { n.classes[c] = (on === undefined) ? !n.classes[c] : !!on; },
        add(c) { n.classes[c] = true; },
        remove(c) { n.classes[c] = false; },
        contains(c) { return !!n.classes[c]; },
    };
    return n;
}
global.document = {
    body: makeNode('body'),
    getElementById(id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement() { return makeNode(null); },
    addEventListener() {},
};
global.window = global;
global.performance = { now: function () { return 0; } };

// --- taklit sahne ------------------------------------------------------
let yuklu = senaryo.loadedMetric || null;   // sahnede yüklü alanın metriği
const cagrilar = [];
function metricOf(id) {
    for (let i = 0; i < CFD_METRICS.length; i++) {
        if (CFD_METRICS[i].id === id) return CFD_METRICS[i];
    }
    return null;
}
function durum(id) {
    return { metric: id, range: senaryo.range || { min: 0.115, max: 2.912 },
             cells: { axial: 60, radial: 12 },
             stations: { shown: 60, total: 60 },
             decimated: !!senaryo.decimated };
}
const viz = {
    state: { cutaway: true, labels: true, plume: true, exploded: false,
             autoRotate: false, portShape: 'circular', playing: false,
             heatMap: false },
    dims: { burnTime: 10 },
    getHeatInfo() { return null; },
    getCfdField() { return yuklu ? durum(yuklu) : null; },
    setCfdMetric(id) {
        cagrilar.push({ fn: 'setCfdMetric', id: id });
        if (!yuklu) {
            return { ok: false, reason: { code: 'no_field',
                key: 'viz3d.cfd.err.noField', fallback: 'stub', params: {} } };
        }
        if ((senaryo.missing || []).indexOf(id) >= 0) {
            return { ok: false, reason: { code: 'missing_metric',
                key: 'viz3d.cfd.err.missingMetric', fallback: 'stub',
                params: { metric: id } } };
        }
        yuklu = id;
        return Object.assign({ ok: true }, durum(id),
                             { unitLabel: metricOf(id).unit });
    },
    clearCfdField() {
        cagrilar.push({ fn: 'clearCfdField' });
        const vardi = yuklu !== null;
        yuklu = null;
        return vardi;
    },
    setPortShape() {}, cyclePortShape() {}, cycleCameraPreset() { return 'iso'; },
    setQuality() {}, cycleSpeed() { return 1; }, snapshot() { return null; },
    setCutaway() {}, setLabels() {}, setPlume() {}, setExploded() {},
    setAutoRotate() {}, resetCamera() {}, play() {}, pause() {}, setTime() {},
    update() {},
};
global.MotorViz3D = {
    isSupported() { return true; },
    mount() { return viz; },
    update() {},
    CFD_METRICS: CFD_METRICS,
    CFD_COLORSCALES: CFD_COLORSCALES,
};

require(process.argv[2]);
const host = document.getElementById('deck_host');
const deck = window.MotorVizDeck.create('deck_host',
    { chamber_diameter: 0.1, chamber_length: 0.3, throat_diameter: 0.02,
      exit_diameter: 0.04, chamber_pressure: 20, thrust: 5000, isp: 250,
      burn_time: 10, viz_motor_type: 'solid' },
    { motorType: 'solid' });

function dump() {
    const p = deck.prefix;
    const dugmeler = {};
    CFD_METRICS.forEach(function (m) {
        const b = nodes[p + '_cfd_m_' + m.id];
        dugmeler[m.id] = b ? { disabled: !!b.disabled, active: !!b.classes.active,
                               text: b.textContent, title: b.title } : null;
    });
    return {
        prefix: p,
        hostHtml: host.innerHTML,
        buttons: dugmeler,
        off: nodes[p + '_cfd_off']
            ? { disabled: !!nodes[p + '_cfd_off'].disabled } : null,
        range: nodes[p + '_cfd_range'] ? nodes[p + '_cfd_range'].textContent : null,
        status: nodes[p + '_cfd_status'] ? nodes[p + '_cfd_status'].textContent : null,
        calls: cagrilar,
    };
}

const out = { before: dump() };
(senaryo.click || []).forEach(function (id) {
    const n = nodes[deck.prefix + id];
    if (n && n.onclick) n.onclick();
});
out.after = dump();
process.stdout.write(JSON.stringify(out));
"""


def kos_guverte(tmp_path, **senaryo):
    betik = tmp_path / 'kos_deck.js'
    betik.write_text(
        DECK_HARNESS.replace('/*VIZ3D_TABLES*/',
                             bildirim(VIZ3D_JS, 'CFD_COLORSCALES') + '\n'
                             + bildirim(VIZ3D_JS, 'CFD_METRICS')),
        encoding='utf-8')
    p = subprocess.run([NODE, str(betik), str(DECK_JS), json.dumps(senaryo)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, 'güverte node altında çöktü:\n' + p.stderr[-2500:]
    return json.loads(p.stdout)


class TestGuverteDenetimleri:
    def test_grup_basiliyor_ve_alan_yokken_gri(self, tmp_path):
        out = kos_guverte(tmp_path)
        b = out['before']
        assert 'CFD FIELD' in b['hostHtml'], 'CFD denetim grubu hiç basılmamış'
        assert all(d['disabled'] for d in b['buttons'].values()), (
            'alan yokken metrik düğmeleri açık — sahte düğme')
        assert b['off']['disabled'] is True, 'alan yokken kapat düğmesi açık'
        assert b['range'] == '—', 'alan yokken uydurma aralık basılmış'
        assert 'No CFD field is loaded' in b['status'], (
            'grubun neden gri olduğu yazılmamış: %r' % b['status'])
        assert not b['calls'], 'güverte kendiliğinden sahneye çağrı yapmış'

    def test_her_metrik_icin_dugme_var(self, tmp_path, viz3d_metrics):
        out = kos_guverte(tmp_path)
        kume_esitligi(out['before']['buttons'].keys(),
                      [m['id'] for m in viz3d_metrics],
                      'güverte düğmeleri', 'CFD_METRICS')
        for m in viz3d_metrics:
            d = out['before']['buttons'][m['id']]
            assert d['title'] == m['labelFallback'], (
                '%s düğmesinin künyesi sahnenin etiketi değil: %r'
                % (m['id'], d['title']))

    def test_alan_yuklendiginde_grup_acilir(self, tmp_path):
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          range={'min': 0.115, 'max': 2.912})
        b = out['before']
        assert not any(d['disabled'] for d in b['buttons'].values())
        assert b['off']['disabled'] is False
        assert b['buttons']['mach']['active'] is True, (
            'yüklü metriğin düğmesi vurgulanmamış')
        # Aralık SAHNENİN döndürdüğü sayılardır
        assert '0.115' in b['range'] and '2.912' in b['range'], (
            'aralık sahnenin sözlüğünden gelmiyor: %r' % b['range'])
        assert 'Showing' in b['status'] and '60/60' in b['status']

    def test_metrik_dugmesi_sahneyi_cagirir_ve_araligi_yazar(self, tmp_path):
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          range={'min': 1622.83, 'max': 2996.73},
                          click=['_cfd_m_temperature'])
        cagrilar = [c for c in out['after']['calls']
                    if c['fn'] == 'setCfdMetric']
        assert cagrilar and cagrilar[-1]['id'] == 'temperature'
        a = out['after']
        assert a['buttons']['temperature']['active'] is True
        assert '1622.830' in a['range'] and '2996.730' in a['range'], (
            'yeni aralık güvertede gösterilmiyor: %r' % a['range'])
        assert 'K' in a['range'], 'birim etiketi (K) yazılmamış'

    def test_yukte_olmayan_metrik_adiyla_beyan_edilir(self, tmp_path):
        """Sahne 'missing_metric' derse güverte nedenini yazar ve o düğmeyi
        kapatır — sessizce hiçbir şey olmamış gibi davranmaz."""
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          missing=['temperature'],
                          click=['_cfd_m_temperature'])
        a = out['after']
        assert 'missing_metric' in a['status'], (
            'red kodu adıyla yazılmamış: %r' % a['status'])
        assert 'metric=temperature' in a['status'], (
            'red parametreleri gizlenmiş: %r' % a['status'])
        assert a['buttons']['temperature']['disabled'] is True, (
            'yükte olmayan büyüklüğün düğmesi açık bırakılmış')
        assert a['buttons']['mach']['active'] is True, (
            'başarısız geçiş sonrası gösterilen metrik kaymış')

    def test_kapat_dugmesi_katmani_soker(self, tmp_path):
        out = kos_guverte(tmp_path, loadedMetric='pressure',
                          click=['_cfd_off'])
        assert any(c['fn'] == 'clearCfdField' for c in out['after']['calls'])
        a = out['after']
        assert all(d['disabled'] for d in a['buttons'].values()), (
            'alan kaldırıldıktan sonra düğmeler açık kalmış')
        assert a['range'] == '—'
        assert 'removed from the scene' in a['status']

    def test_inceltme_beyani_tasiniyor(self, tmp_path):
        out = kos_guverte(tmp_path, loadedMetric='mach', decimated=True)
        assert 'thinned' in out['before']['status'], (
            'inceltme beyanı güvertede kaybolmuş: %r'
            % out['before']['status'])

    def test_guvertede_sahte_gosterge_yok(self):
        """Güvertenin CFD bölümünde zamanlayıcı ya da rastgelelik YOK:
        durum sahnenin GERÇEK beyanından okunur."""
        temiz = strip_js_comments(_oku(DECK_JS))
        cfd_bolumu = temiz[temiz.index('cfdSetStatus'):temiz.index('designSliderValue')]
        for yasak in ('setInterval', 'setTimeout', 'Math.random',
                      'requestAnimationFrame'):
            assert yasak not in cfd_bolumu, (
                'CFD denetim grubunda %s var — sahte ilerleme yolu' % yasak)
