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
import re
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
    """OH-GT-07 — pano reddedilince veri kaybolmaz.

    V301/N-YZ (26 Eki 2026) — KOD TAŞINDI, KORUMA KALDI. Üç sayfanın ayrı
    ``askAI`` / pano / veri penceresi kopyası (app.js, solid.html,
    liquid.html) tek ortak modüle ``hrma/static/js/ai_assistant.js``
    ("Yapay Zekâ ile Tasarla") taşındı. Bu sınıfın sayfa başına ölçtüğü üç
    koruma (hata dalında pencere, adıyla loglama, pano API'si yokken senkron
    fırlatmama) artık o modülde ve node altında GERÇEK gövdeyle
    ``tests/test_v301_yapay_zeka.py::TestPanoDaliOrtakModul`` tarafından
    koşturuluyor. Burada kalan: taban kusurunun kaydı + sayfaların kendi
    pano kopyasını yeniden edinmediği + modülün üç korumayı taşıdığı.
    """

    YZ_MODUL_YOLU = REPO_ROOT / 'hrma' / 'static' / 'js' / 'ai_assistant.js'

    def test_taban_kusuru_gerceklesti(self, taban):
        """Taban: üç sayfanın HİÇBİRİNDE hata dalında modal yoktu."""
        k1 = taban['K1_OH_GT_07_pano_dali']
        assert [k1[f]['hata_dalinda_modal'] for f in SAYFALAR] == \
            [False, False, False]

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_sayfa_kendi_pano_kopyasini_tasimaz(self, olcum, sayfa):
        """Üç sayfa ortak modülü kullanır; ikinci bir pano yolu doğmaz."""
        k1 = olcum.k1()
        assert not k1[sayfa]['zincir_var'], (
            '%s yeniden kendi pano kopyasını taşıyor; ortak modül '
            'ai_assistant.js kullanılmalı (V301/N-YZ)' % sayfa)
        assert not k1['modal_fonksiyonu_tanimli'][sayfa]

    def test_modul_uc_korumayi_tasir(self):
        """Hata dalında pencere + adıyla log + senkron fırlatma koruması."""
        src = self.YZ_MODUL_YOLU.read_text(encoding='utf-8')
        k = src.find('Panel.prototype.metniVer')
        assert k >= 0, 'ai_assistant.js metniVer bulunamadı'
        govde = src[k:src.find('\n    };', k)]
        catch = govde[govde.find('.catch('):]
        assert 'metinPenceresi(' in catch, 'hata dalında pencere açılmıyor'
        assert 'panoHataMetni(err)' in catch, 'hata adıyla yazılmıyor'
        assert not re.search(r'console\.(?:error|warn)\([^;]*,\s*err\s*\)', catch)
        p = src.find('function panoyaYaz(')
        assert re.search(r'nav\.clipboard\s*&&', src[p:p + 600]), (
            'clipboard API yokluğu karşılanmıyor')
        assert 'Promise.reject(err)' in src[p:p + 600], (
            'senkron fırlatma söze çevrilmiyor')

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
