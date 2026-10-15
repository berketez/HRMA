"""ÖH Dalga-34 · kulvar **js-davranis** · aşama a1 — BEKÇİ.

21 Eylül 2026 görsel kabul turunun (Cowork) beş "basit" bulgusunu kilitler.
Bekçi kendi ölçütünü yeniden yazmaz: ölçüm
``docs/scofield/raw/OH/D34/js-davranis/a1/olcum.py`` betiğinindir, buradaki
iddialar onun SAYILARINI sınar. Nerede mümkünse ölçüm KAYNAK DİZESİ değil
DAVRANIŞ okur — ilgili fonksiyon node altında gerçekten koşturulur.

Kalemler ve ÖLÇÜLEN kusur (``a1/once.json``, taban ``5c07c625``):

==========  =========================================  ==================
Kalem       Kusur                                      Önce → Sonra
==========  =========================================  ==================
OH-GT-07    pano reddedilince "Yapay zekâya yorumlat"  hata dalında modal
            verisi tümüyle kayboluyor (üç sayfa)       yok → var (3/3)
OH-GT-08    3B ölçü künyesi dayanağı kaynağa bakmıyor  yalan 2 → 0
OH-GT-09    kapalı dışa aktarım düğmesi nedenini       title yok → var,
            söylemiyor, imleci hâlâ ``pointer``        imleç kuralı yok → var
OH-GT-10    yayın sürümünde geliştirme günlükleri      kapısız 30 → 0
OH-GT-11    port büyümesi grafiği başlıksız            boş → dolu
==========  =========================================  ==================

TERS-MUTASYON: her iddia ``a1/mutasyon.py`` ile kırmızıya çevrilmiş
durumda kanıtlanmıştır (``a1/mutasyon.json``).
"""

import importlib.util
import json
import pathlib
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
KANIT = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D34' / 'js-davranis' / 'a1'
OLCUM_PY = KANIT / 'olcum.py'
ONCE_JSON = KANIT / 'once.json'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

SAYFALAR = ('app.js', 'liquid.html', 'solid.html')


def _olcum_modulu():
    spec = importlib.util.spec_from_file_location('d34_js_olcum', kanit_gerekli(OLCUM_PY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def olcum():
    assert kanit_gerekli(OLCUM_PY).exists(), 'ölçüm betiği yok: %s' % OLCUM_PY
    return _olcum_modulu()


@pytest.fixture(scope='module')
def taban():
    """Taban (onarım öncesi) ölçümü — kusurun GERÇEKTEN var olduğunun kaydı.

    Bekçinin kendi ölçütünü doğrular: ``once.json`` kusuru göstermiyorsa
    buradaki "sonra" iddiaları boş bir şeyi koruyor demektir.
    """
    assert kanit_gerekli(ONCE_JSON).exists(), 'taban ölçümü yok: %s' % ONCE_JSON
    return json.loads(kanit_gerekli(ONCE_JSON).read_text(encoding='utf-8'))


def _node(betik):
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# OH-GT-07 — pano başarısızsa veri kaybolmaz
# ---------------------------------------------------------------------------

class TestGT07PanoDali:

    def test_taban_kusuru_gerceklesti(self, taban):
        """Taban: üç sayfanın HİÇBİRİNDE hata dalında modal yoktu."""
        k1 = taban['K1_OH_GT_07_pano_dali']
        assert [k1[f]['hata_dalinda_modal'] for f in SAYFALAR] == \
            [False, False, False]

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_hata_dalinda_veri_penceresi_acilir(self, olcum, sayfa):
        k1 = olcum.k1()
        assert k1[sayfa]['hata_dalinda_modal'], (
            '%s: pano reddedilince veri penceresi açılmıyor — özellik '
            'sessizce kayboluyor (OH-GT-07)' % sayfa)

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_ham_hata_nesnesi_loglanmiyor(self, olcum, sayfa):
        """``console.error(..., err)`` DOMException'ı "{}" diye basıyordu."""
        k1 = olcum.k1()
        assert not k1[sayfa]['ham_err_logluyor'], (
            '%s: hata nesnesi ham loglanıyor; ad + ileti yazılmalı' % sayfa)

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_pano_apisi_yoksa_senkron_firlatmaz(self, olcum, sayfa):
        """Güvensiz bağlamda ``navigator.clipboard`` UNDEFINED'dır."""
        k1 = olcum.k1()
        assert k1[sayfa]['pano_api_yoksa_korumasi'], (
            '%s: clipboard API yokluğu karşılanmıyor; `.writeText` senkron '
            'fırlatır ve `.catch` hiç koşmaz' % sayfa)

    @pytest.mark.parametrize('sayfa', ('liquid.html', 'solid.html'))
    def test_modal_davranisi_node_altinda(self, olcum, sayfa):
        """ÜRÜN KOŞUMU: şablonun kendi ``showAIDataModal``ı koşturulur."""
        src = olcum.oku(olcum.SABLON / sayfa)
        parcalar = [olcum.govde(src, ad)
                    for ad in ('kacisliMetin', 'showAIDataModal')]
        assert all(parcalar), '%s: modal yardımcıları bulunamadı' % sayfa
        betik = """
'use strict';
var _eklenen = [];
function dugum() {
    return { attrs: {}, style: { cssText: '' }, __html: '',
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) { return this.attrs[k] || null; },
        addEventListener: function () {}, remove: function () {},
        appendChild: function (c) { _eklenen.push(c); return c; },
        get innerHTML() { return this.__html; },
        set innerHTML(v) { this.__html = String(v); } };
}
var _body = dugum();
global.document = {
    createElement: function () { return dugum(); },
    getElementById: function () { return null; },
    addEventListener: function () {}, removeEventListener: function () {},
    body: _body
};
global.window = global;
function T(key, fallback) { return fallback; }
""" + '\n'.join(parcalar) + """
showAIDataModal('VERI <script>alert(1)</script> SON', 'PANO REDDEDILDI');
var m = _eklenen[0] || null;
process.stdout.write(JSON.stringify({
    eklendi: !!m,
    id: m && m.id,
    role: m && m.getAttribute('role'),
    giris_var: !!(m && m.innerHTML.indexOf('PANO REDDEDILDI') >= 0),
    veri_var: !!(m && m.innerHTML.indexOf('VERI') >= 0),
    ham_etiket_var: !!(m && m.innerHTML.indexOf('<script>alert') >= 0),
    kacisli: !!(m && m.innerHTML.indexOf('&lt;script&gt;') >= 0)
}));
"""
        out = _node(betik)
        assert out['eklendi'], '%s: pencere belgeye eklenmiyor' % sayfa
        assert out['id'] == 'aiModal'
        assert out['role'] == 'dialog'
        assert out['giris_var'], '%s: uyarı metni pencerede yok' % sayfa
        assert out['veri_var'], '%s: veri pencerede yok' % sayfa
        assert not out['ham_etiket_var'] and out['kacisli'], (
            '%s: veri HTML olarak kaçışsız basılıyor' % sayfa)

    def test_app_js_modal_giris_metni_devralinabilir(self, olcum):
        """``showAIDataModal(data, prompt, giris)`` üçüncü argümanı basmalı.

        Aksi hâlde hata dalında "panoya kopyalandı" YALANI görünürdü.
        """
        src = olcum.oku(olcum.APP_JS)
        fn = olcum.govde(src, 'showAIDataModal')
        assert fn, 'app.js showAIDataModal bulunamadı'
        betik = """
'use strict';
var _eklenen = [];
global.document = { body: { insertAdjacentHTML: function (nerede, html) {
    _eklenen.push(html); } } };
global.window = global;
function T(key, fallback) { return fallback; }
""" + fn + """
showAIDataModal({}, 'PROMPT', 'KOPYALANAMADI');
showAIDataModal({}, 'PROMPT');
process.stdout.write(JSON.stringify({
    ozel: _eklenen[0].indexOf('KOPYALANAMADI') >= 0,
    ozelde_varsayilan_yok: _eklenen[0].indexOf('copied to your clipboard') < 0,
    varsayilan: _eklenen[1].indexOf('copied to your clipboard') >= 0
}));
"""
        out = _node(betik)
        assert out['ozel'], 'giriş metni devralınmıyor'
        assert out['ozelde_varsayilan_yok'], (
            'hata dalında hâlâ "panoya kopyalandı" metni basılıyor')
        assert out['varsayilan'], 'varsayılan giriş metni kayboldu'


# ---------------------------------------------------------------------------
# OH-GT-08 — 3B ölçü künyesinin dayanağı kaynağa bakar
# ---------------------------------------------------------------------------

class TestGT08KunyeDayanagi:

    def test_taban_kusuru_gerceklesti(self, taban):
        assert taban['K2_OH_GT_08_kunye_dayanagi']['yalan_sayisi'] == 2

    def test_kunye_yalani_kalmadi(self, olcum):
        k2 = olcum.k2()
        assert 'node_hatasi' not in k2, k2.get('node_hatasi')
        assert k2['yalan_sayisi'] == 0, (
            'künye çözücü değerini kullanıp dayanak olarak uydurma oranı '
            'gösteriyor (OH-GT-08): %s' % json.dumps(k2, ensure_ascii=False))

    @pytest.mark.parametrize('yuk,beklenen_kind,beklenen_basis', [
        ('a_grain_design', 'computed', 'solver: grain_design.grain_length_mm'),
        ('b_motor_grain_length', 'computed', 'solver: motor.grain_length'),
        ('c_yedek', 'assumed', 'fallback 0.8·Lch'),
    ])
    def test_dayanak_degerin_geldigi_dali_soyluyor(
            self, olcum, yuk, beklenen_kind, beklenen_basis):
        """ÜRÜN KOŞUMU: node altında GERÇEK ``extractDims`` çalışır."""
        k2 = olcum.k2()
        gl = k2[yuk]['grain_length']
        assert gl['kind'] == beklenen_kind
        assert gl['basis'] == beklenen_basis

    def test_deger_ile_dayanak_ayrismiyor(self, olcum):
        """Çözücü 511,533 mm yayımladıysa künye de onu göstermeli."""
        k2 = olcum.k2()
        assert k2['a_grain_design']['Lg_mm'] == pytest.approx(511.533)
        assert 'fallback' not in k2['a_grain_design']['grain_length']['basis']
        # Kardeş alanlar tabanda da doğruydu; daralmadıklarını kilitle.
        assert k2['a_grain_design']['chamber_diameter']['basis'] == \
            'solver: motor.chamber_diameter'
        assert k2['a_grain_design']['grain_outer_diameter']['basis'] == \
            'grain_design.outer_diameter_mm'


# ---------------------------------------------------------------------------
# OH-GT-09 — kapalı dışa aktarım düğmesi nedenini söyler
# ---------------------------------------------------------------------------

class TestGT09KapaliDugme:

    def test_taban_kusuru_gerceklesti(self, taban):
        k3 = taban['K3_OH_GT_09_kapali_dugme']
        assert k3['disabled_var'] and not k3['title_var']
        assert not k3['sablonda_btn_disabled_imleci']

    def test_kapali_dugme_nedenini_soyluyor(self, olcum):
        """ÜRÜN KOŞUMU: ``setExportResultsEnabled`` node altında koşar."""
        d = olcum.k3()['davranis']
        assert 'node_hatasi' not in d, d.get('node_hatasi')
        assert d['kapali']['disabled'] is True
        assert d['kapali']['title'], (
            'kapalı düğme NEDEN kapalı olduğunu söylemiyor (OH-GT-09)')
        assert d['acik']['disabled'] is False
        assert not d['acik']['title'], (
            'düğme açıldıktan sonra bayat ipucu kalıyor')

    def test_imlec_tiklanabilir_gostermiyor(self, olcum):
        assert olcum.k3()['sablonda_btn_disabled_imleci'], (
            'kapalı .btn imleci hâlâ pointer — düğme tıklanabilir görünüyor')


# ---------------------------------------------------------------------------
# OH-GT-10 — yayın sürümünde geliştirme günlüğü yok
# ---------------------------------------------------------------------------

class TestGT10KonsolGurultusu:

    def test_taban_kusuru_gerceklesti(self, taban):
        assert taban['K4_OH_GT_10_konsol_gurultusu']['kapisiz_toplam'] == 30

    def test_kapisiz_console_log_kalmadi(self, olcum):
        k4 = olcum.k4()
        ayrinti = {ad: k4[ad]['kapisiz_satirlar'] for ad in
                   ('app.js', 'advanced.html', 'liquid.html', 'solid.html')
                   if k4[ad]['kapisiz']}
        assert k4['kapisiz_toplam'] == 0, (
            'yayın sürümünde kapısız console.log kaldı: %s' % ayrinti)

    @pytest.mark.parametrize('ad', ('app.js', 'advanced.html',
                                    'liquid.html', 'solid.html'))
    def test_hata_kanallari_vakumlanmadi(self, olcum, taban, ad):
        """``console.error``/``warn`` TEŞHİSTİR — süpürme onları almamalı."""
        k4 = olcum.k4()
        t = taban['K4_OH_GT_10_konsol_gurultusu'][ad]
        assert k4[ad]['console_error'] >= t['console_error']
        assert k4[ad]['console_warn'] >= t['console_warn']


# ---------------------------------------------------------------------------
# OH-GT-11 — port büyümesi grafiğinin başlığı
# ---------------------------------------------------------------------------

class TestGT11GrafikBasligi:

    def test_taban_kusuru_gerceklesti(self, taban):
        k5 = taban['K5_OH_GT_11_grafik_basligi']
        assert k5['gercek_seri']['baslik_bos'] is True

    @pytest.mark.parametrize('dal', ('gercek_seri', 'dogrusal_tahmin'))
    def test_her_dalda_baslik_var(self, olcum, dal):
        """ÜRÜN KOŞUMU: grafik node altında GERÇEKTEN çizilir."""
        k5 = olcum.k5()
        assert 'node_hatasi' not in k5, k5.get('node_hatasi')
        assert not k5[dal]['baslik_bos'], (
            '%s dalında Plotly başlığı boş (OH-GT-11)' % dal)

    def test_dogrusal_tahmin_uyarisi_kaybolmadi(self, olcum):
        """Başlık eklenirken eski uyarı metni YUTULMAMALI."""
        k5 = olcum.k5()
        assert 'Linear estimate' in k5['dogrusal_tahmin']['baslik']
        assert 'Linear estimate' not in k5['gercek_seri']['baslik'], (
            'gerçek seride doğrusal tahmin uyarısı görünüyor — YALAN')

    def test_eksen_etiketleri_daralmadi(self, olcum, taban):
        k5, t = olcum.k5(), taban['K5_OH_GT_11_grafik_basligi']
        for dal in ('gercek_seri', 'dogrusal_tahmin'):
            for eksen in ('eksen_x', 'eksen_y', 'eksen_y2'):
                assert k5[dal][eksen] == t[dal][eksen]
            assert k5[dal]['seri_sayisi'] == t[dal]['seri_sayisi']


# ---------------------------------------------------------------------------
# Sözdizimi — dokunulan her dosya
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('yol', [
    'hrma/static/js/app.js', 'hrma/static/js/motor_viz3d.js'])
def test_js_sozdizimi(yol):
    res = subprocess.run([NODE, '--check', str(REPO_ROOT / yol)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
