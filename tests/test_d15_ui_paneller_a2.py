# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / kulvar ui-paneller, aşama 2 — bekçiler.

Kapsanan defter kalemleri:

* **P11B4-04** [yüksek] ``structural_panel.js`` beş emniyet katsayısı
  hücresini de YEŞİL basıyordu; oysa uç aynı koşumda
  ``safety_factor_is_tautological`` haritasında beş modun beşini de
  ``true`` ilan ediyor ve gerekçesini yazıyor: sayı, kullanıcının kendi
  hedefinin geri okumasıdır ("input read back, NOT an independent
  verification"). Z4-B turunda yalnız İM eklenmiş, RENGE dokunulmamıştı.
* **P11B4-05** [yüksek] "BUCKLING: SAFE" yeşil rozeti, uygulanan eksenel
  yük SIFIR ve ``axial_buckling_safety_factor`` NULL iken basılıyordu;
  yükün hangi durumda olduğunu söyleyen alanlar (``governing_load_case``,
  ``axial_compression_force_N``, ``pressure_stabilizing_stress_MPa`` ve
  ucun kendi 300+ karakterlik gerekçesi) ekrana hiç çıkmıyordu.
* **P11B4-09** [yüksek] ``joint_panel.js`` üç emniyet kartını da NOMİNAL
  ön-yükten boyuyordu; modülün kendi ``governing_basis`` beyanına göre
  bağlayıcı olan kötü-durum değerlerinin ikisi 1,0'ın ALTINDA
  (``proof_SF_min`` 0,990 · ``overload_factor_nL_min`` 0,861) ve ekranda
  SAYI olarak hiç yoktu.
* **P11B2-08** [yüksek] Tasarım raporu "Total Propellant Mass" satırında
  YANAN itergacı yazıyor, "Total Mass" satırında YÜKLENEN kütleyi
  gösteriyordu; grenin yanmayan payı (``fuel_sliver_fraction``) ve
  yüklenen gren (``fuel_mass_loaded``) rapora hiç inmiyordu.
* **P11B2-24** [yüksek] ``app.js`` "başarı" rozetini YALNIZ
  ``response.ok``'a bakarak basıyordu: geometrisi tümüyle ``null`` bir CAD
  yanıtına yeşil onay + etkin STL düğmesi, PDF olmayan bir 200 yanıtına
  ``.pdf`` adıyla indirme, İSTENMEYEN taramayı döndüren bir 200 yanıtına
  "completed successfully".
* **P11B4-12** [yüksek] — defter başlığı ("termal eksen SABİT 2,0/5 yeşil,
  300→5000 K'de puan değişmiyor") bu HEAD'de ÖLÇÜMLE ÇÜRÜTÜLDÜ. Buradaki
  iki bekçi ÇÜRÜTMEYİ KİLİTLER: eksen hazne sıcaklığıyla gerçekten
  oynuyor ve ısı zinciri boşken hüküm geri çekiliyor.

Yöntem: ölçüm okumaya değil GERÇEK KOŞUMA dayanır — uçlar Flask
``test_client`` ile çağrılır, paneller ``docs/scofield/raw/P11/B4-repro-03.js``
taklit DOM'unda gerçekten render edilir, ``app.js`` işleyicileri taklit
``fetch`` altında koşturulur. Beklenen değerler ürün sabitlerinden
TÜRETİLMEZ (ÖK / H2): her iddia ucun O KOŞUMDAKİ yanıtından okunur.

Ham kanıt: ``docs/scofield/raw/OH/D15/ui-paneller/a2/``
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
HARNESS = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'
KAPI_OLCUMU = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15'
               / 'ui-paneller' / 'a2' / 'olc_b2_24.js')
CALC_YANIT = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15'
              / 'ui-paneller' / 'a1' / '_calc_yanit.json')

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — panelleri GERÇEK render altında ölçen '
           'bekçiler koşamaz (kurulum: `brew install node`)')

YESIL = 'var(--hd-green'


# ---------------------------------------------------------------------------
# Ortak koşum yardımcıları
# ---------------------------------------------------------------------------
def _test_client():
    os.environ.setdefault(
        'HRMA_USER_DATA_DIR',
        os.path.join(tempfile.gettempdir(), 'hrma-d15-uip-a2-bekci'))
    from hrma.app import app
    return app.test_client()


def _uc_yuku(endpoint, govde):
    """Ucu GERÇEKTEN çağırır ve yanıtı diske yazıp yolunu döndürür."""
    c = _test_client()
    r = c.post(endpoint, json=govde)
    assert r.status_code == 200, '%s HTTP %s' % (endpoint, r.status_code)
    body = r.get_json()
    fd, yol = tempfile.mkstemp(suffix='.json', prefix='d15a2-')
    with os.fdopen(fd, 'w') as f:
        json.dump({'body': body}, f)
    return yol, body


def _render(panel_id, veri_yolu, panel_dosyasi):
    cfg = {'panelId': panel_id, 'dataFile': veri_yolu,
           'panelFiles': ['hrma/static/js/panels/' + panel_dosyasi]}
    p = subprocess.run([NODE, kanit_gerekli(str(HARNESS))], input=json.dumps(cfg),
                       capture_output=True, text=True,
                       cwd=str(REPO_ROOT), timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    out = json.loads(p.stdout)
    assert not out.get('error'), out['error']
    return out


def _satir_rengi(html, etiket, pencere=900):
    """Etiketin bulunduğu satırdaki İLK renk jetonu (yoksa None)."""
    i = html.find(etiket)
    if i < 0:
        return None
    m = re.search(r'color:\s*(var\(--hd-[a-z-]+)', html[i:i + pencere])
    return m.group(1) if m else None


# Panel varsayılan alanları — panellerin KENDİ FIELDS listelerinden.
#
# ÖH D15 birleştirme (1 Eyl 2026) — ``chamber_temperature: 0`` BURADAN ÇIKTI.
# Yük panelin FIELDS listesini izler ve o liste değişti: alanın varsayılanı
# artık BOŞ DİZE ('' = "termali atla"), 0 değil. Gerekçe panelde ölçümüyle
# yazılı — özeti: yapısal kulvarın sıcaklık kapısı birleştikten sonra 0,
# ``must_be_positive`` ile 422 alıyordu ve bu panelin KENDİ varsayılan
# koşumunu kırıyordu; 0 K mutlak sıcaklıkta fiziksel bir değer olduğu için
# kapı gevşetilmedi, sentinel boş dizeye taşındı (analysis_dock buildPayload
# boş alanı payload'a KOYMAZ, yani alan gönderilmez).
#
# Aşağıdaki iddiaların ÖNCÜLLERİ bu değişimden ETKİLENMEDİ — yeni gövdeyle
# yeniden ölçüldü: ``thermal_analysis.status = NOT_MODELLED`` (termal yol
# eskisi gibi atlanıyor), ``axial_buckling_safety_factor = None``,
# ``axial_compression_force_N = 0.0``, ``governing_load_case = unpressurized``
# ve ``safety_factor_is_tautological`` beş modda da ``True``.
YAPISAL_GOVDE = {
    'chamber_pressure': 40, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.02,
    'thrust': 0, 'wall_thickness': 0, 'material': 'steel_4130',
}
CIVATA_GOVDE = {
    'pressure_bar': 40, 'seal_diameter_mm': 100, 'bolt_count': 8,
    'size': 'M8', 'property_class': '8.8', 'grip_length_mm': 20,
    'member_material': 'aluminum_6061', 'lubricated': 'false',
    'reusable': 'true',
}
GUVENLIK_GOVDE = {
    'motor_type': 'hybrid', 'chamber_pressure': 40,
    'chamber_temperature': 3000, 'thrust': 1000, 'burn_time': 10,
    'propellant_mass': 5, 'propellant_type': 'composite',
    'facility_type': 'test_stand', 'chamber_diameter': 0.1,
    'wall_thickness': 0.005, 'material': 'steel_4130',
}

MOD_ETIKETI = {
    'chamber_hoop': 'Chamber hoop', 'chamber_von_mises': 'Chamber von Mises',
    'end_cap': 'End cap', 'nozzle': 'Nozzle throat',
    'buckling_axial': 'Axial buckling',
}


@pytest.fixture(scope='module')
def yapisal():
    yol, body = _uc_yuku('/analyze_structural_safety', YAPISAL_GOVDE)
    try:
        yield body, _render('structural', yol, 'structural_panel.js')
    finally:
        os.unlink(yol)


def _termal_tarama(zincirli):
    c = _test_client()
    out = []
    for T in (300, 1500, 3000, 3600, 5000):
        g = dict(GUVENLIK_GOVDE)
        g['chamber_temperature'] = T
        if zincirli:
            g['wall_temperature_hot'] = T * 0.9
            g['wall_temperature_cold'] = T * 0.85
        r = c.post('/analyze_safety', json=g)
        assert r.status_code == 200, 'HTTP %s' % r.status_code
        sa = r.get_json()['safety_analysis']
        out.append({
            'T': T,
            'risk': sa['risk_assessment']['individual_risks'].get('thermal'),
            'cidar': sa['thermal_safety'].get('estimated_wall_temperature_k'),
            'oneri': sa['thermal_safety'].get('material_recommendation'),
        })
    return out


@pytest.fixture(scope='module')
def termal_zincirli():
    return _termal_tarama(True)


@pytest.fixture(scope='module')
def termal_bos():
    return _termal_tarama(False)


@pytest.fixture(scope='module')
def rapor_olcumu():
    betik = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15'
             / 'ui-paneller' / 'a2' / 'olc_b2_08.js')
    p = subprocess.run([NODE, kanit_gerekli(str(betik)), kanit_gerekli(str(CALC_YANIT))],
                       capture_output=True, text=True,
                       cwd=str(REPO_ROOT), timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    out = json.loads(p.stdout)
    assert out['render_hatasi'] is None, out['render_hatasi']
    return out


@pytest.fixture(scope='module')
def kapi_olcumu():
    # Uçların boş gövdeye GERÇEK yanıtları (ölçüm anında alınır).
    c = _test_client()
    bos = {}
    # ÖH D15 fix-4 (ana model, 1 Eyl 2026): /parametric-analysis'in zaman
    # bütçesi kapısı makine yüklüyken (measured_seconds_per_point ~2,75 s)
    # boş gövdeyi 422 parametric_time_budget_exceeded ile reddediyor ve JS
    # kapı betiği 'parametrik_ikame' dalını dolduramıyordu (KeyError). Ölçüm
    # ikameyi hedefler, bütçeyi değil: yalnız bütçe tavanı verilir (300 s,
    # ucun kendi üst sınırı), tarama parametresi yine GÖNDERİLMEZ.
    GOVDE = {'cad': {}, 'pdf': {}, 'param': {'time_budget_s': 300}}
    for ad, uc in (('cad', '/api/export-cad'),
                   ('pdf', '/api/export-pdf/summary'),
                   ('param', '/parametric-analysis')):
        r = c.post(uc, json=GOVDE[ad])
        ct = r.headers.get('Content-Type', '')
        bos[ad] = {'status': r.status_code, 'content_type': ct,
                   'bayt': len(r.data),
                   'body': r.get_json() if 'json' in ct else None}
    fd, yol = tempfile.mkstemp(suffix='.json', prefix='d15a2-bos-')
    with os.fdopen(fd, 'w') as f:
        json.dump(bos, f, default=str)
    try:
        p = subprocess.run([NODE, kanit_gerekli(str(KAPI_OLCUMU)), yol],
                           capture_output=True, text=True,
                           cwd=str(REPO_ROOT), timeout=300)
        assert p.returncode == 0, p.stderr[-3000:]
        return json.loads(p.stdout)
    finally:
        os.unlink(yol)


@pytest.fixture(scope='module')
def civata():
    yol, body = _uc_yuku('/api/bolted-joint', CIVATA_GOVDE)
    try:
        yield body, _render('joint', yol, 'joint_panel.js')
    finally:
        os.unlink(yol)


# ---------------------------------------------------------------------------
# P11B4-04 — totolojik emniyet katsayısı YEŞİL basılamaz
# ---------------------------------------------------------------------------
@node_gerekli
class TestTotolojikEmniyetKatsayisi:

    def test_totolojik_mod_satiri_yesil_hukum_tasimaz(self, yapisal):
        body, r = yapisal
        sa = body['structural_analysis']['safety_analysis']
        taut = sa.get('safety_factor_is_tautological') or {}
        # Bu koşumda ucun gerçekten totolojik dediği modlar olmalı; yoksa
        # bekçi bir şey ölçmüyor demektir (boş-geçme koruması).
        totolojik = [k for k, v in taut.items() if v is True]
        assert totolojik, ('uç bu koşumda hiçbir modu totolojik ilan etmedi; '
                           'bekçinin ölçeceği kusur yok — gövde değişmiş olabilir')
        html = r['html']
        # Mod satırı: '&nbsp;&nbsp;· <ad>' hücresinin YANINDAKİ sayı hücresi.
        renkler = dict(re.findall(
            r'&nbsp;&nbsp;· ([A-Za-z ]+)</strong>\s*</td>\s*<td[^>]*>\s*'
            r'<span style="color:(var\(--hd-[a-z-]+)', html))
        assert renkler, 'mod satırı hiç bulunamadı — render biçimi değişmiş'
        for k in totolojik:
            et = MOD_ETIKETI.get(k)
            if et is None or et not in renkler:
                continue
            assert renkler[et] != YESIL, (
                '%s modu ucun kendi beyanına göre TOTOLOJİK '
                '(safety_factor_is_tautological=%r) ama ekranda YEŞİL '
                'hüküm basılıyor; yeşil "sınandı ve geçti" demektir, '
                'totolojik sayı sınanmamıştır' % (et, taut[k]))

    def test_oda_bloklari_totolojikken_manset_satirlari_yesil_degil(self, yapisal):
        body, r = yapisal
        ca = body['structural_analysis']['chamber_analysis']
        if ca.get('safety_factor_is_tautological') is not True:
            pytest.skip('uç bu koşumda oda bloğunu totolojik ilan etmedi')
        html = r['html']
        for et in ('SF (pressure only)', 'SF (total, incl. thermal)'):
            renk = _satir_rengi(html, et, pencere=2000)
            assert renk is not None, '%s satırı ekranda yok' % et
            assert renk != YESIL, (
                '%s satırı YEŞİL basılıyor ama chamber_analysis'
                '.safety_factor_is_tautological=True — gerekçe: %r'
                % (et, str(ca.get('safety_factor_basis'))[:120]))

    def test_totolojik_satirda_ucun_alan_adi_yaziyor(self, yapisal):
        body, r = yapisal
        sa = body['structural_analysis']['safety_analysis']
        taut = sa.get('safety_factor_is_tautological') or {}
        n = len([k for k, v in taut.items() if v is True])
        if not n:
            pytest.skip('bu koşumda totolojik mod yok')
        # Renk tek başına yetmez: hangi alanın bunu söylediği de ekranda
        # olmalı (kullanıcı sönük sayının NEDEN hükümsüz olduğunu okusun).
        assert r['html'].count('safety_factor_is_tautological') >= n, (
            'totolojik mod sayısı %d ama ekranda o kadar alan adı imi yok' % n)


# ---------------------------------------------------------------------------
# P11B4-05 — kazanılmamış burkulma hükmü
# ---------------------------------------------------------------------------
@node_gerekli
class TestBurkulmaHukmu:

    def test_emniyet_katsayisi_yokken_rozet_yesil_basilmaz(self, yapisal):
        body, r = yapisal
        buck = body['structural_analysis']['buckling_analysis']
        if buck.get('axial_buckling_safety_factor') is not None:
            pytest.skip('bu koşumda burkulma emniyet katsayısı yayımlandı')
        assert 'BUCKLING' in r['text'], 'burkulma rozeti ekranda yok'
        html = r['html']
        i = html.find('BUCKLING')
        m = re.search(r'color:\s*(var\(--hd-[a-z-]+)', html[max(0, i - 500):i + 500])
        assert m, 'burkulma rozetinin rengi okunamadı'
        assert m.group(1) != YESIL, (
            'axial_buckling_safety_factor=None, applied_axial_stress_MPa=%r '
            'iken rozet YEŞİL basılıyor — hesap hiç eksenel yük görmedi, '
            '"SAFE" bir ölçüm değil yükün yokluğudur'
            % buck.get('applied_axial_stress_MPa'))

    def test_yuk_durumu_alanlari_ekranda(self, yapisal):
        # ÖNEMLİ (ters mutasyonda yakalandı): "alan adı html'de geçiyor mu"
        # yetmez — ucun kendi `applied_axial_stress_pressurized_basis`
        # cümlesi `axial_compression_force_N` ve
        # `pressure_stabilizing_stress_MPa` adlarını METİN İÇİNDE anıyor.
        # O yüzden burada alanın SATIR olarak, DEĞERİYLE basıldığı ölçülür.
        body, r = yapisal
        buck = body['structural_analysis']['buckling_analysis']
        metin = r['text']
        for alan in ('governing_load_case', 'axial_compression_force_N',
                     'pressure_stabilizing_stress_MPa'):
            v = buck.get(alan)
            if v is None:
                continue
            beklenen = ('%.2f' % v) if isinstance(v, (int, float)) else str(v)
            # Satır dizilimi: <alan adı> <değer>  (aradaki birim serbest)
            assert re.search(re.escape(alan) + r'\s+' + re.escape(beklenen),
                             metin), (
                'uç %s=%r yayımlıyor ama ekranda o alanın DEĞERİYLE '
                'basıldığı bir satır yok (yalnız başka bir cümlenin içinde '
                'anılması yeterli değil)' % (alan, v))

    def test_ucun_sifir_gerekcesi_ekranda_yaziyor(self, yapisal):
        body, r = yapisal
        buck = body['structural_analysis']['buckling_analysis']
        gerekce = buck.get('applied_axial_stress_pressurized_basis')
        if not gerekce:
            pytest.skip('uç bu koşumda gerekçe yayımlamadı')
        # Rozetin `title` niteliği SAYILMAZ: üzerine gelmeden okunmayan bir
        # metin ekranda değildir. Gerekçe kendi paragrafında, alan adıyla
        # birlikte basılmalı.
        html = r['html']
        m = re.search(
            r'<p[^>]*>\s*<span[^>]*>\s*applied_axial_stress_pressurized_basis'
            r'\s*</span>\s*:\s*(.{0,80})', html, re.S)
        assert m, ('ucun kendi gerekçesi ("0 tam olarak sıfırdır, eksik '
                   'model değil") ekranda kendi paragrafında basılmıyor')
        assert gerekce[:30] in html, 'gerekçe metni ekrana inmiyor'


# ---------------------------------------------------------------------------
# P11B4-09 — cıvata kartlarının hükmü YÖNETİCİ değerden okunur
# ---------------------------------------------------------------------------
@node_gerekli
class TestCivataYoneticiEmniyet:

    CIFTLER = (
        ('proof_SF', 'proof_SF_min', 'Proof SF'),
        ('overload_factor_nL', 'overload_factor_nL_min', 'Overload factor n_L'),
        ('separation_factor_n0', 'separation_factor_n0_min',
         'Separation factor n0'),
    )

    def test_yonetici_deger_bir_altindayken_kart_yesil_basilmaz(self, civata):
        body, r = civata
        sf = body['joint']['safety_factors']
        html = r['html']
        olculen = 0
        for nom, yon, et in self.CIFTLER:
            v = sf.get(yon)
            if not isinstance(v, (int, float)) or v >= 1.0:
                continue
            olculen += 1
            renk = _satir_rengi(html, et)
            assert renk is not None, '%s kartı ekranda yok' % et
            assert renk != YESIL, (
                '%s kartı YEŞİL ama modülün kendi yönetici ölçütüne göre '
                'bağlayıcı olan %s = %.4f, yani 1,0 ALTINDA. governing_basis: %r'
                % (et, yon, v, str(sf.get('governing_basis'))[:120]))
        assert olculen, ('bu koşumda 1,0 altında yönetici değer yok — '
                         'bekçinin ölçeceği kusur yok, gövde değişmiş olabilir')

    def test_yonetici_sayilar_ekranda(self, civata):
        body, r = civata
        sf = body['joint']['safety_factors']
        metin = r['text']
        for _nom, yon, _et in self.CIFTLER:
            v = sf.get(yon)
            if not isinstance(v, (int, float)):
                continue
            assert ('%.3f' % v) in metin, (
                '%s = %.4f bağlayıcı değer ama ekranda SAYI olarak yok'
                % (yon, v))

    def test_yonetici_deger_bir_ustundeyken_kart_yesil_kalir(self, civata):
        """Aşırı düzeltme koruması: yönetici değer sağlamsa hüküm YEŞİL kalır."""
        body, r = civata
        sf = body['joint']['safety_factors']
        html = r['html']
        for nom, yon, et in self.CIFTLER:
            v = sf.get(yon)
            nv = sf.get(nom)
            if not isinstance(v, (int, float)) or not isinstance(nv, (int, float)):
                continue
            # n0 eşiği sfKind varsayılanı 1,5; proof/nL için 1,2.
            esik = 1.5 if yon.startswith('separation') else 1.2
            if v < esik:
                continue
            assert _satir_rengi(html, et) == YESIL, (
                '%s kartı: yönetici değer %s = %.4f eşiğin (%.1f) üstünde '
                'olmasına rağmen yeşil hüküm düşmüş — aşırı düzeltme'
                % (et, yon, v, esik))


# ---------------------------------------------------------------------------
# P11B2-08 — yanan kütle ⟷ yüklenen kütle
# ---------------------------------------------------------------------------
@node_gerekli
class TestKutleButcesi:

    def test_yuklenen_gren_ve_yanmayan_pay_rapora_iner(self, rapor_olcumu):
        out = rapor_olcumu
        uc = out['uc']
        # Çelişki bu koşumda GERÇEKTEN var olmalı; yoksa bekçi boş geçer.
        assert out['celiski_kg'] and abs(out['celiski_kg']) > 1e-9, (
            'bu koşumda yanan ⟷ yüklenen farkı yok; bekçinin ölçeceği '
            'kusur yok')
        for alan in ('fuel_mass_loaded', 'fuel_sliver_fraction'):
            assert uc[alan] is not None, 'uç %s yayımlamıyor' % alan
            assert out['ekranda'][alan] is True, (
                'çözücü %s = %r yayımlıyor ve rapordaki "Total Propellant '
                'Mass" (%.4f kg) ile "Total Mass" (%.4f kg) arasında '
                '%.4f kg (%%%.2f) fark var, ama bu alan ekrana hiç inmiyor'
                % (alan, uc[alan], uc['propellant_mass_total_yanan'],
                   uc['total_mass_kg'], out['celiski_kg'],
                   out['celiski_yuzde']))

    def test_kutle_dayanagi_cumleleri_rapora_iner(self, rapor_olcumu):
        out = rapor_olcumu
        for alan in ('total_mass_basis', 'dry_mass_basis'):
            if not out['uc'][alan + '_var']:
                continue
            assert out['ekranda'][alan] is True, (
                'çözücü %s beyanını yayımlıyor (iki kütle satırı arasındaki '
                'farkı açıklayan tek cümle) ama rapora inmiyor' % alan)

    def test_yanan_satirlar_hala_basiliyor(self, rapor_olcumu):
        """Gerileme koruması: eski satırlar kaybolmadı."""
        out = rapor_olcumu
        for alan in ('propellant_mass_total', 'fuel_mass_yanan',
                     'oxidizer_mass', 'total_mass_kg'):
            assert out['ekranda'][alan] is True, (
                '%s satırı rapordan kayboldu' % alan)


# ---------------------------------------------------------------------------
# P11B2-24 — dışa aktarım "başarı" rozetinin içerik kapısı
# ---------------------------------------------------------------------------
@node_gerekli
class TestDisaAktarimIcerikKapisi:

    def test_kazanilmamis_cad_yaniti_basari_yayimlamaz(self, kapi_olcumu):
        """İçeriği KAZANILMAMIŞ bir CAD yanıtında yeşil onay çıkmaz.

        ÖH D31 fix-34b — SÖZLEŞME DEĞİŞTİ, bekçi yeni sözleşmeyi okuyor.
        Eski senaryo ``/api/export-cad``in "200 ama geometri özeti tamamen
        null" yanıtını kuruyordu ve ölçüm ``app.js::generateCAD``i
        koşturuyordu. O uç ÜRÜN YÜZÜNDEN KOPUK (fix-34a §3) ve o kopya
        ÖLÜYDÜ; D30 arayuz-panel a1 (``896d2e83``) onu söktü, ölçüm de
        ``{_yok: 'generateCAD'}`` döndürüp bu düğümü KeyError'a
        düşürüyordu. Kullanıcının gördüğü akış ``advanced.html``in satır
        içi ``generateCAD``idir; 3B görünümün tek kaynağı
        ``/api/generate-3d``dir (fail-closed dalı OH-D23-15).

        İDDİA AYNEN: uç 3B'yi üretemediyse ekran "başarıyla üretildi"
        demez, STL indirme düğmesi ETKİNLEŞMEZ ve sebep söylenir.
        """
        out = kapi_olcumu
        r = out['CAD_3d_kazanilmadi']
        assert r['kayit']['basari'] == [], (
            '3B görünüm üretilemediği hâlde ekrana yeşil onay çıktı: %r'
            % r['kayit']['basari'])
        assert r['stlDugmesi_etkin'] is not True, (
            'kazanılmamış bir CAD akışında STL indirme düğmesi ETKİNLEŞTİ')
        assert r['kayit']['hata'], 'kapı kapandı ama kullanıcıya sebep söylenmedi'

    def test_kazanilmis_cad_akisi_hala_tamamlaniyor(self, kapi_olcumu):
        """Aşırı düzeltme koruması: geçerli 3B yanıtında akış tamamlanır."""
        assert kapi_olcumu['cad_kazanildiginda_tamamlaniyor'] is True, (
            'geçerli plot_data gelmesine rağmen CAD akışı tamamlanmadı — '
            'kapı fazla kapandı: %r' % (kapi_olcumu['CAD_3d_kazanildi'],))

    def test_pdf_olmayan_200_indirilmez(self, kapi_olcumu):
        out = kapi_olcumu
        assert out['PDF_html200']['kayit']['indirilen'] == [], (
            '200 dönen HTML hata sayfası .pdf adıyla indi: %r'
            % out['PDF_html200']['kayit']['indirilen'])

    def test_gercek_pdf_hala_iniyor(self, kapi_olcumu):
        """Aşırı düzeltme koruması: geçerli PDF engellenmemeli."""
        out = kapi_olcumu
        assert out['gercek_pdf_hala_iniyor'] is True, (
            'doğru içerik tipli, %PDF- imzalı gerçek PDF de indirilemez '
            'oldu — kapı fazla kapandı')

    def test_istenmeyen_tarama_basari_yayimlamaz(self, kapi_olcumu):
        """Uç istenmeyen bir tarama döndürürse ekran "başarılı" DEMEZ.

        ÖH D28 fix-28b — SÖZLEŞME DEĞİŞTİ, bekçi yeni sözleşmeyi okuyor.
        D28 app-api a1 (4a332738, OH-D27-03) ucu fail-closed yaptı: adı
        verilmeyen tarama artık İKAME EDİLMİYOR, HTTP 422
        ``sweep_parameter_not_supplied`` ile reddediliyor. Bu ölçümün
        gövdesi ``param_type``'ı BİLEREK göndermez (ikameyi arar), yani
        bugün ucun cevabı reddir. Eski bekçi bu durumda ölçemiyordu:
        ``donen_parametre`` anahtarı JS ölçümünde düşüyor ve test KeyError
        veriyordu.

        Kusur ARANMAYA DEVAM EDİYOR, yalnız iki bacağa ayrıldı:
          * uç bir tarama DÖNDÜRDÜYSE ve bu istenenden başkaysa -> ekran
            başarı yayımlamamalı, ayrışmayı söylemeli (eski iddia, aynen);
          * uç REDDETTİYSE -> ekran o reddi de başarı diye yayımlamamalı ve
            kullanıcıya söylemeli. Reddin ADI da ölçülür, çünkü ucun
            fail-closed kapısı sökülüp yerine sessiz bir 200 konursa bu
            bekçi kırmızıya dönmelidir.
        """
        out = kapi_olcumu
        ik = out['parametrik_ikame']
        kayit = out['PARAM']['kayit']
        donen = ik['donen_parametre']
        # ÖH D31 fix-34b: ölçüm CANLI `advanced.html::calculateParametric`
        # üstünde koşuyor (app.js kopyası D30 panel a1'de söküldü). İKAME
        # BACAĞI ölü bırakılmaz: uç 200 + BAŞKA eksen döndürdüğünde
        # `assertParametricMatchesRequest` kapısı ayrı bir senaryoyla
        # sınanır — aşağıdaki `donen is None` dalı ucun BUGÜNKÜ reddini
        # ölçtüğü için o dal tek başına ikameyi göremezdi.
        ikame = out['parametrik_ikame_kapisi']
        assert ikame['basari'] == [], (
            'uç istenenden BAŞKA bir eksen (of_ratio) taradı ve ekran yine '
            '"başarılı" dedi: %r' % ikame['basari'])
        assert ikame['hata'], (
            'eksen ikamesi kullanıcıya söylenmedi — sunucu yankısı kapısı '
            '(assertParametricMatchesRequest) canlı yolda koşmuyor')
        if donen is None:
            assert ik['uc_durumu'] == 422 and \
                ik['uc_reddi'] == 'sweep_parameter_not_supplied', (
                    'uç hiçbir tarama parametresi döndürmedi ama bunu adıyla '
                    'da REDDETMEDİ (durum %r, red %r) — adı verilmeyen bir '
                    'eksen için sessiz cevap, ikamenin kendisi kadar '
                    'okunaksızdır (OH-D27-03 kapısı)'
                    % (ik['uc_durumu'], ik['uc_reddi']))
            assert kayit['basari'] == [], (
                'uç taramayı %r diye REDDETTİ, ekran yine de "başarılı" dedi: '
                '%r' % (ik['uc_reddi'], kayit['basari']))
            assert kayit['hata'], 'ret kullanıcıya söylenmedi'
            return
        if donen == ik['istenen_parametre']:
            pytest.skip('uç bu koşumda ikame yapmadı')
        assert kayit['basari'] == [], (
            '%r istendi, uç %r taraması döndürdü ve ekran "başarılı" dedi'
            % (ik['istenen_parametre'], donen))
        assert kayit['hata'], 'ayrışma kullanıcıya söylenmedi'

    def test_uc_kapinin_hicbiri_kazanilmamis_hukum_yayimlamiyor(self, kapi_olcumu):
        out = kapi_olcumu
        assert out['icerik_bos_ama_basari_yayimlayan'] == 0, (
            'içeriği kazanılmamış %d uçta hâlâ başarı yayımlanıyor'
            % out['icerik_bos_ama_basari_yayimlayan'])


# ---------------------------------------------------------------------------
# P11B4-12 — ÇÜRÜTÜLEN başlığın kilidi: termal eksen CANLI
# ---------------------------------------------------------------------------
class TestTermalEksenCanli:
    """Defter başlığı "termal eksen SABİT 2,0/5" bu HEAD'de ÇÜRÜK.

    Bu iki bekçi çürütmeyi kilitler: eksen hazne sıcaklığına gerçekten
    yanıt veriyor ve ısı zinciri boşken hüküm geri çekiliyor. Başlığın
    tarif ettiği kusur geri gelirse ikisi de kırmızıya döner.
    """

    def test_termal_puan_hazne_sicakligiyla_degisir(self, termal_zincirli):
        t = termal_zincirli
        puanlar = [x['risk'] for x in t]
        assert all(p is not None for p in puanlar), (
            'ısı zinciri DOLUYKEN bile termal puan yayımlanmıyor: %r' % puanlar)
        assert len(set(puanlar)) > 1, (
            '300→5000 K arasında termal puan SABİT kaldı: %r — defter '
            'P11B4-12 kusuru geri gelmiş' % puanlar)
        cidarlar = [x['cidar'] for x in t]
        assert len(set(cidarlar)) > 1, (
            'cidar sıcaklığı hazne sıcaklığından bağımsız çakılı: %r' % cidarlar)
        # Yön: sıcaklık artarken risk azalmamalı (monoton artan olmalı).
        assert puanlar == sorted(puanlar), (
            'hazne sıcaklığı artarken termal risk düşüyor: %r' % puanlar)

    def test_isi_zinciri_bossa_termal_hukum_geri_cekilir(self, termal_bos):
        t = termal_bos
        for x in t:
            assert x['risk'] is None, (
                'ısı zinciri BOŞ (kullanıcı cidar sıcaklığı vermedi) ama '
                'T=%s K için termal risk puanı %r yayımlandı — sessiz '
                'varsayılan' % (x['T'], x['risk']))
            assert x['cidar'] is None, (
                'ısı zinciri boşken cidar sıcaklığı %r uyduruldu' % x['cidar'])

    @node_gerekli
    def test_hukum_geri_cekilince_ekran_yesil_puan_basmaz(self):
        yol, body = _uc_yuku('/analyze_safety',
                             dict(GUVENLIK_GOVDE, chamber_temperature=3600))
        try:
            r = _render('safety', yol, 'safety_panel.js')
        finally:
            os.unlink(yol)
        ir = body['safety_analysis']['risk_assessment']['individual_risks']
        if ir.get('thermal') is not None:
            pytest.skip('bu koşumda uç termal puanı yayımladı')
        metin = r['text']
        assert 'Thermal' in metin, 'termal ekseni ekranda hiç yok'
        i = r['html'].find('Thermal')
        pencere = r['html'][i:i + 900]
        assert not re.search(r'\d+\.\d+\s*/\s*5', pencere), (
            'uç termal hükmü geri çektiği hâlde ekranda puan basılıyor: %r'
            % pencere[:200])
        assert YESIL not in pencere, (
            'kazanılmamış termal hüküm YEŞİL basılıyor')


# ===========================================================================
# ÖH D15 birleştirme bekçisi — PANELİN KENDİ VARSAYILANI KOŞABİLMELİ
# ===========================================================================
# NEDEN VAR: bu dosyanın üç gövdesi (``YAPISAL_GOVDE`` / ``CIVATA_GOVDE`` /
# ``GUVENLIK_GOVDE``) "panellerin KENDİ FIELDS listelerinden" diye yazılmıştı
# ama bunu ÖLÇEN hiçbir şey yoktu — bağ yalnız yorumda duruyordu. D15
# birleştirmesinde bedeli ödendi: yapısal kulvarın sıcaklık kapısı panelin
# ``chamber_temperature`` varsayılanını (0) reddetmeye başladı, panel
# değişmedi ve KİMSE görmedi; kullanıcı paneli açıp Run'a bastığında 422
# alıyordu, bu dosyanın altı bekçisi ise yalnız "fikstür hatası" veriyordu.
#
# Bu iki bekçi bağı ÖLÇÜLEBİLİR kılar:
#   1. Gövdeler panelin gerçek ``register()`` spec'inden türetilenle aynı mı,
#   2. O yük ucun kendisi tarafından KABUL ediliyor mu (HTTP 200).
# Alanlar ürün kodundan gelir: panel dosyası node içinde GERÇEKTEN koşturulur
# ve ``AnalysisDock.register`` çağrısı yakalanır; testin kendi kopyası değil.

#: Panel dosyalarını koşturup ``register()`` spec'ini JSON olarak basar.
_SPEC_TOPLAMA_JS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const dosya = process.argv[2];
let yakalanan = null;
const El = function () { this.style = {}; this.innerHTML = ''; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.appendChild = function () {};
El.prototype.addEventListener = function () {};
const doc = {
    createElement: function () { return new El(); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
    body: new El(),
};
const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    setTimeout, clearTimeout, setInterval, clearInterval,
    fetch: () => Promise.reject(new Error('sandbox: ag yok')),
    JSON, Math, Number, Array, Object, String, Boolean, RegExp, Date,
    Promise, isFinite, parseFloat, parseInt, document: doc,
    AnalysisDock: { ui: {}, util: {}, register: function (s) {
        yakalanan = { id: s.id, endpoint: s.endpoint || null,
                      fields: (s.fields || []).map(f => [f[0], f[2]]) };
    } },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(dosya, 'utf8'), sandbox, { filename: dosya });
if (!yakalanan) { throw new Error('register() cagrilmadi: ' + dosya); }
process.stdout.write(JSON.stringify(yakalanan));
"""


def _panel_spec(panel_dosyasi):
    """Panelin ``register()`` spec'i — ÜRÜN kodundan, gerçek koşumla."""
    betik = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                        encoding='utf-8')
    try:
        betik.write(_SPEC_TOPLAMA_JS)
        betik.close()
        p = subprocess.run(
            [NODE, betik.name, str(PANELS_DIR / panel_dosyasi)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
        assert p.returncode == 0, p.stderr[-2000:]
        return json.loads(p.stdout)
    finally:
        os.unlink(betik.name)


def _varsayilan_yuk(spec):
    """Panelin varsayılan alanlarından dock'un KENDİ kuralıyla kurulan yük.

    Kural ``analysis_dock.js:buildPayload``: alanın değeri sonlu bir sayıya
    çözülürse payload'a KONUR, çözülmezse (boş dize) KONMAZ — ve
    ``requiredFieldInfo`` sayısal olmayan varsayılanı isteğe bağlı sayar,
    yani istek yine de gönderilir. Seçim kutuları (dizi) ilk seçeneği verir.
    """
    yuk = {}
    for ad, varsayilan in spec['fields']:
        if isinstance(varsayilan, bool):
            continue
        if isinstance(varsayilan, (int, float)):
            yuk[ad] = varsayilan
        elif isinstance(varsayilan, str) and varsayilan != '':
            yuk[ad] = varsayilan
        elif isinstance(varsayilan, list) and varsayilan:
            yuk[ad] = varsayilan[0]
    return yuk


#: ÇEVRİLEN BEKÇİ (ÖH D36 · onemli2-sivi a2). Güvenlik panelinin
#: ``burn_time`` (10 s) ve ``propellant_mass`` (5 kg) varsayılanları KALKTI
#: (Berke onaylı LU-1'in fail-closed kuralı: süresiz sıvıda çözücü ikisini
#: de yayımlamıyor ve panel nöbetçileri kullanıcının girdisi gibi
#: gidiyordu; ölçüm docs/scofield/raw/OH/D36/onemli2-sivi/a2/). Panelin
#: VARSAYILAN gövdesi artık ikisini TAŞIMAZ. ``GUVENLIK_GOVDE`` bu dosyanın
#: diğer bekçileri için hüküm alan TAM gövde olarak kalır; varsayılan-koşum
#: bekçileri panelin gerçek varsayılanını (aşağıdaki gövde) ölçer.
GUVENLIK_VARSAYILAN_GOVDE = {k: v for k, v in GUVENLIK_GOVDE.items()
                             if k not in ('burn_time', 'propellant_mass')}

#: Varsayılan koşumu BİLEREK hükümsüz olan paneller: uç 422 + eksik alanın
#: ADI döner. Bekçinin asıl derdi (panel varsayılanı ucun kapısında
#: GEÇERSİZ sayılmasın: D15'teki 0 K sıcaklık) korunur — eksik alan
#: eklenince aynı gövde 200 almalı, yani kalan her varsayılan geçerli.
_VARSAYILANI_ADIYLA_EKSIK = {
    'safety_panel.js': ('incomplete_safety_input', ['propellant_mass'],
                        {'propellant_mass': 5.0}),
}

#: (panel dosyası, uç, bu dosyanın o panel için kullandığı gövde)
_PANEL_GOVDELERI = [
    ('structural_panel.js', '/analyze_structural_safety', YAPISAL_GOVDE),
    ('joint_panel.js', '/api/bolted-joint', CIVATA_GOVDE),
    ('safety_panel.js', '/analyze_safety', GUVENLIK_VARSAYILAN_GOVDE),
]


class TestPanelVarsayilaniKosabilir:
    """Panelin varsayılan durumu ucun kapısından geçmeli (D15 birleştirme)."""

    @node_gerekli
    @pytest.mark.parametrize('panel,uc,govde', _PANEL_GOVDELERI,
                             ids=[x[0] for x in _PANEL_GOVDELERI])
    def test_bu_dosyanin_govdesi_panelin_alanlariyla_ayni(self, panel, uc,
                                                          govde):
        """Yorumdaki "panelin KENDİ FIELDS listesinden" iddiası ölçülür."""
        spec = _panel_spec(panel)
        assert spec['endpoint'] == uc, (
            '%s artık %r ucunu çağırıyor — bu dosyanın gövdesi başka uca '
            'gidiyor' % (panel, spec['endpoint']))
        beklenen = _varsayilan_yuk(spec)
        # Bu dosya bazı alanları BİLEREK panelden farklı kurar (ör. güvenlik
        # gövdesi ısı zincirini uyandırmak için sıcaklık verir). Ölçülen
        # iddia dar: panelin varsayılanında BULUNAN bir alan gövdede de
        # bulunmalı, ve gövdedeki her alan panelin alanlarından biri olmalı.
        panel_alanlari = {ad for ad, _ in spec['fields']}
        yabanci = sorted(set(govde) - panel_alanlari)
        assert not yabanci, (
            '%s gövdesinde panelde OLMAYAN alan var: %s — gövde panelin '
            'alanlarını izlemiyor' % (panel, yabanci))
        eksik = sorted(set(beklenen) - set(govde))
        assert not eksik, (
            '%s varsayılan olarak %s alanlarını da GÖNDERİYOR, bu dosyanın '
            'gövdesinde yoklar — gövde panelin varsayılanının gerisinde '
            'kaldı' % (panel, eksik))
        gonderilmeyen = sorted(set(govde) & (panel_alanlari - set(beklenen)))
        assert not gonderilmeyen, (
            '%s bu alanları varsayılan durumda GÖNDERMİYOR (boş alan), ama '
            'gövde gönderiyor: %s — gövde artık panelin varsayılan koşumunu '
            'temsil etmiyor' % (panel, gonderilmeyen))

    @pytest.mark.parametrize('panel,uc,govde', _PANEL_GOVDELERI,
                             ids=[x[0] for x in _PANEL_GOVDELERI])
    def test_panelin_varsayilan_yuku_ucun_kapisindan_gecer(self, panel, uc,
                                                           govde):
        """Kullanıcı paneli açıp Run'a bastığında hüküm alır, 4xx değil.

        ÖLÇÜLDÜ (1 Eyl 2026, birleşik ağaç): ``chamber_temperature`` alanının
        0 varsayılanı ``/analyze_structural_safety`` kapısından 422
        ``invalid_structural_input`` ile dönüyordu.
        """
        c = _test_client()
        r = c.post(uc, json=govde, headers={'Host': '127.0.0.1:8080'})
        if panel in _VARSAYILANI_ADIYLA_EKSIK:
            kod, eksik, tamamlayan = _VARSAYILANI_ADIYLA_EKSIK[panel]
            j = r.get_json() or {}
            assert r.status_code == 422, (panel, r.status_code, j)
            assert j.get('error') == kod and j.get('missing_fields') == eksik, j
            assert not j.get('invalid_fields'), (
                '%s varsayılanında GEÇERSİZ alan var: %s'
                % (panel, j.get('invalid_fields')))
            r = c.post(uc, json=dict(govde, **tamamlayan),
                       headers={'Host': '127.0.0.1:8080'})
        assert r.status_code == 200, (
            '%s panelinin varsayılan yükü %s ucundan HTTP %s aldı: %s'
            % (panel, uc, r.status_code,
               json.dumps(r.get_json(), ensure_ascii=False)[:500]))

    def test_sicaklik_verilmeyince_termal_yol_ATLANIR(self):
        """Sentinel'in ANLAMI korunuyor mu — taşıyıcısı değişti diye kayboldu mu.

        ``chamber_temperature`` alanı artık boş varsayılanla geliyor (0
        değil). Uç bu durumda termal yolu KOŞMAMALI ve bunu BEYAN etmeli;
        sessizce bir termal hüküm uydurmamalı.
        """
        c = _test_client()
        body = c.post('/analyze_structural_safety', json=YAPISAL_GOVDE,
                      headers={'Host': '127.0.0.1:8080'}).get_json()
        sa = body['structural_analysis']
        termal = sa.get('thermal_analysis') or {}
        assert termal.get('status') == 'NOT_MODELLED', (
            'gaz sıcaklığı verilmedi ama termal yol koştu: %r'
            % termal.get('status'))
        assert 'not run' in str(termal.get('basis', '')).lower(), (
            'termal yolun atlandığı BEYAN edilmiyor: %r' % termal.get('basis'))
        assert (sa.get('safety_analysis') or {}).get(
            'thermal_margin_ratio') is None, (
            'ısı girdisi yokken termal marj uyduruldu')
