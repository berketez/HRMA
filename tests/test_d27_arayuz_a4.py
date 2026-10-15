# -*- coding: utf-8 -*-
"""ÖH Dalga-27 · arayuz kulvarı · aşama-4 bekçileri.

Kalemler: P11B4-29, P11B5-10..17, P11S1-02, P11S1-05 (+ aşama-2'nin
bıraktığı `transient_panel.js` regresyonu).

Ölçüm betiği: docs/scofield/raw/OH/D27/arayuz/a4/olcum.py
Ters mutasyon: docs/scofield/raw/OH/D27/arayuz/a4/mutasyon.py
"""
import json
import pathlib
import re
import subprocess
import shutil

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


def oku(rel):
    return (KOK / rel).read_text(encoding='utf-8')


def kes_fonksiyon(kaynak: str, ad: str) -> str:
    """Bir üst-düzey JS fonksiyonunu kaynaktan süslü-parantez sayarak keser."""
    bas = kaynak.index('\n    function %s(' % ad)
    i = kaynak.index('{', bas + len(ad) + 12)
    derinlik, son = 0, i
    while son < len(kaynak):
        if kaynak[son] == '{':
            derinlik += 1
        elif kaynak[son] == '}':
            derinlik -= 1
            if derinlik == 0:
                break
        son += 1
    return kaynak[bas + 1:son + 1]


def node_kos(tmp_path, betik: str):
    yol = tmp_path / 'kos.js'
    yol.write_text(betik, encoding='utf-8')
    p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')



def _js_yorumsuz_dizesiz(src):
    """JS kaynağından yorumları VE dize sabitlerini ayıklar.

    ÖH D33-KOLAY · P11B5-14 ŞARTI. ``test_viz3d_render_kalite`` içindeki
    ``_strip_comments`` yalnız yorumu atar; kullanıcıya basılan DİZE
    sabitinde geçen alan adı oradan da görünür kalır. Burada ikisi de
    ayıklanır: kalan metin YALNIZ koddur.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in '"\'`':
            q = c
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(c)
        i += 1
    return ''.join(out)


# ===========================================================================
# REGRESYON (aşama-2 borcu) — transient_panel.js çıplak yedeği
# ===========================================================================

class TestTransientAyrilmaFailClosed:
    """`steps_floored` gelmediğinde ekrana UYDURULMUŞ bir 0 çıkmaz."""

    def test_ciplak_yedek_yok(self):
        js = oku('hrma/static/js/transient_panel.js')
        assert 'Number(fsep.steps_floored) || 0' not in js, (
            'çözücü alanının çıplak `|| 0` yedeği geri geldi: alan '
            'gelmediğinde panel "0/N adım" diye uydurulmuş bir sayı basar '
            've rozeti YEŞİL yapar — "ölçüm yok" ile "ayrılma yok" aynı '
            'ekranı verir (tests/test_ui_no_fabricated_numbers.py bunu '
            'beyansız yedek olarak KIRMIZI ile yakalar).')

    def test_alan_yoksa_adiyla_reddedilir(self):
        js = oku('hrma/static/js/transient_panel.js')
        assert 'transient.badgeSeparationUnknown' in js
        assert 'steps_floored NOT REPORTED' in js


# ===========================================================================
# P11B4-29 — kök-yeri penceresinin künyesi + simetri ölçümü
# ===========================================================================

class TestP11B429KokYeriPenceresi:

    def test_basis_ekrana_iner(self):
        js = oku('hrma/static/js/panels/stability_panel.js')
        assert 'rl._basis' in js, (
            'root_locus._basis panelde okunmuyor — pencerenin nasıl '
            'kurulduğunu (ve kırpıldığını) anlatan TEK metin ekran dışında.')
        assert "greyBlock('locus-basis'" in js

    @node_gerekli
    def test_asimetrik_pencere_sayiyla_olculur(self, tmp_path):
        src = oku('hrma/static/js/panels/stability_panel.js')
        govde = kes_fonksiyon(src, 'locusWindowSymmetry')
        tol = re.search(r'const LOCUS_SYMMETRY_REL_TOL = ([0-9.eE+-]+);', src)
        assert tol, 'tolerans sabiti tek kaynakta değil'
        betik = (
            'const LOCUS_SYMMETRY_REL_TOL = %s;\n'
            'function isNum(v){return typeof v==="number"&&isFinite(v);}\n'
            % tol.group(1)
            + govde
            + '\nconst simetrik = locusWindowSymmetry('
              '{dp_ratio_j:[1,2,3]}, {dp_ratio_j:2});\n'
              'const kirpik = locusWindowSymmetry('
              '{dp_ratio_j:[1,2,3]}, {dp_ratio_j:1.2});\n'
              'const yok = locusWindowSymmetry({dp_ratio_j:[1]}, {dp_ratio_j:1});\n'
              'console.log(JSON.stringify({simetrik, kirpik, yok}));\n')
        out = node_kos(tmp_path, betik)
        assert out['simetrik']['symmetric'] is True
        assert out['kirpik']['symmetric'] is False, (
            'pencere merkezi kırpıldığında (J_op kenara yakın) simetri '
            'ölçümü hâlâ "simetrik" diyor')
        # sol kol 0,2 · sağ kol 1,8 → bağıl fark %88,9
        assert abs(out['kirpik']['rel'] - (1.6 / 1.8)) < 1e-9
        assert out['yok'] is None, 'iki noktadan az örnekte hüküm verilmemeli'


# ===========================================================================
# P11B5-10 / P11B5-14 — ÇÜRÜTÜLDÜ; kalem bayat, gerileme bekçisi kurulur
# ===========================================================================

class TestP11B510ErimeEkseniOkunuyor:
    """Kalem 'hiç okunmuyor' diyordu; ölçüm dördünü de okunmuş buldu."""

    ALANLAR = ('exceeds_melting', 'melting_point_K', 'time_to_melting_s',
               'margin_to_melting_K')

    def test_dort_alan_da_panelde_okunur(self):
        js = oku('hrma/static/js/panels/protection_panel.js')
        eksik = [a for a in self.ALANLAR if ('d.%s' % a) not in js]
        assert not eksik, (
            'erime ekseni panelden düştü: %s — erimiş cidar ile servis '
            'limitini 1 K aşan cidar yeniden aynı rozeti alır' % eksik)

    def test_erime_rozeti_servis_rozetinden_ayri(self):
        js = oku('hrma/static/js/panels/protection_panel.js')
        assert 'panel.protection.exceedsMelting' in js
        assert 'panel.protection.limitExceeded' in js


class TestP11B514KirpilanIstasyonlar:
    """Kalem 'ekrana hiç çıkmıyor' diyordu; ölçüm 3 geçiş buldu."""

    def test_kirpilan_istasyon_sayisi_ekranda(self):
        """ÖH D33-KOLAY · P11B5-14 denetim ŞARTI — SAYIM ÖLÇÜTÜ ÇIKARILDI.

        ESKİ ölçüt ``js.count('property_table_clamped_stations') >= 2``
        idi ve KÖRDÜ: ad dosyada ÜÇ kez geçiyor — biri künye YORUMUNDA,
        biri kullanıcıya basılan DİZE sabitinde, yalnız biri gerçek
        OKUMA. ÖLÇÜLDÜ (``a2/once.json`` K1): okuma satırı silindiğinde
        ham geçiş 3 -> 2 düşüyor, yani eşik hâlâ sağlanıyor ve bekçi
        YEŞİL kalıyordu; yorumun kendisi alanın okunduğuna tanıklık
        ediyordu.

        Yeni ölçüt iki ayaklıdır:
          (a) burada — yorum ve dize sabitleri AYIKLANDIKTAN sonra kodda
              kalan geçiş sayılır ve gerçek okuma satırı aranır;
          (b) tests/test_d33_arayuz_panel_a2.py'de — notlar bloğu node
              altında koşturulup notun kırpilan = 0 ve kırpilan = 3 için
              GERÇEKTEN üretildiği ölçülür (tercih edilen ayak).
        """
        ad = 'property_table_clamped_stations'
        js = oku('hrma/static/js/panels/cooling_panel.js')
        temiz = _js_yorumsuz_dizesiz(js)
        assert temiz.count(ad) >= 1, (
            'kırpılan istasyon sayısı panelden düştü: adın kalan geçişleri '
            'yalnız yorum/dize sabitinde — kod alanı OKUMUYOR, kullanıcı '
            'bant dışına düşüp kenara kırpılmış istasyonları ölçülmüş sanır')
        assert 'const kirpilan = sm.%s;' % ad in js, (
            'kırpılan istasyon okuması yeniden yazılmış: bekçi ölçümü '
            'bayatladı, satırı ve a2 davranış bekçisini birlikte güncelle')


# ===========================================================================
# P11B5-11 — blowdown çözünürlük kapısı adlandırıldı ve ilan edilir
# ===========================================================================

class TestP11B511OrneklemSayisi:

    def test_kapi_ciplak_degil(self):
        js = oku('hrma/static/js/blowdown_panel.js')
        assert 'const MIN_POLYLINE_SAMPLES = 2;' in js
        assert 'arr.length < 2' not in js, (
            'çözünürlük kapısı yeniden çıplak sayıya döndü (tek kaynak yok)')
        assert 'arr.length < MIN_POLYLINE_SAMPLES' in js

    @node_gerekli
    def test_ornek_sayisi_rozetle_basilir(self, tmp_path):
        """DAVRANIŞ bekçisi: rozet GERÇEKTEN üretilen HTML'de mi?

        ÖH D33-KOLAY · P11B5-11 denetim ŞARTI — BEKÇİ ÇEVRİLDİ.
        ESKİ ölçüt kaynak METNİNDE dize arıyordu ("'SAMPLES ' + ..." ve
        'not a decay'). O ölçüt KUSURU KORUYORDU: `badge()` İKİ parametre
        alırken örneklem rozeti ÜÇ argümanla çağrılıyordu (depodaki TEK
        üç-argümanlı çağrı), üçüncüsü — açıklama cümlesi — sessizce
        DÜŞÜYORDU. Cümle dosyada VARDI, ekranda YOKTU; bekçi yeşildi.
        Artık `renderBadges` node altında koşturulur ve ÜRETİLEN HTML
        ölçülür.
        """
        src = oku('hrma/static/js/blowdown_panel.js')
        mk = re.search(r'const MIN_POLYLINE_SAMPLES = (\d+);', src)
        assert mk, 'çözünürlük kapısının tek kaynağı yok'
        betik = ('var window = {};\n'
                 + 'const MIN_POLYLINE_SAMPLES = %s;\n' % mk.group(1)
                 + kes_fonksiyon(src, 'T')
                 + kes_fonksiyon(src, 'TF')
                 + kes_fonksiyon(src, 'SRV')
                 + kes_fonksiyon(src, 'esc')
                 + kes_fonksiyon(src, 'escAttr')
                 + kes_fonksiyon(src, 'isInstabilityText')
                 + kes_fonksiyon(src, 'badge')
                 + kes_fonksiyon(src, 'endEventKind')
                 + kes_fonksiyon(src, 'renderBadges')
                 + '\nfunction kos(n) {\n'
                   '  const el = { innerHTML: "" };\n'
                   '  renderBadges(el, { sample_count: n });\n'
                   '  return el.innerHTML;\n'
                   '}\n'
                   'console.log(JSON.stringify('
                   '{az: kos(2), cok: kos(40), yok: kos(null)}));\n')
        out = node_kos(tmp_path, betik)
        # 1) Sayı HER koşumda ekrana çıkar.
        assert 'SAMPLES 2' in out['az'], (
            'örneklem sayısı ekranda yazmıyor: 2 örneklemli düz doğru '
            '"sönüm eğrisi" diye satılır')
        assert 'SAMPLES 40' in out['cok']
        # 2) İki örneklemde rozet UYARI rengindedir, kırkta değil.
        assert 'var(--hd-orange' in out['az'], (
            'iki örneklemli dejenere seri NÖTR renkle "normal" diye '
            'basılıyor')
        assert 'var(--hd-orange' not in out['cok'], (
            'aşırı düzeltme: çözülmüş seride de uyarı rengi var')
        # 3) ŞARTIN ÖZÜ: açıklama ÜRETİLEN HTML'e ulaşıyor.
        assert 'not a decay' in out['az'], (
            'açıklama üretilen HTML\'e hiç ulaşmıyor: `badge()` üçüncü '
            'argümanı yutuyor, kullanıcı iki örneklemli düz doğrunun '
            'neden "eğri" olmadığını HİÇBİR yerde okuyamıyor')
        assert 'title="' in out['az'], 'açıklama bir ipucu özniteliğine yazılmıyor'
        assert 'not a decay' not in out['cok'], (
            'çözülmüş seriye de "eğri değil" açıklaması iliştiriliyor')
        # 4) Alan yoksa rozet UYDURULMAZ.
        assert 'SAMPLES' not in out['yok'], (
            'sample_count yayımlanmamışken rozet uyduruluyor'
        )

    def test_ornek_sayisi_seriden_sayiliyor(self):
        """Rozetin beslendiği sayı görünüm modelinde seriden kurulur."""
        js = oku('hrma/static/js/blowdown_panel.js')
        assert 'base.sample_count = n;' in js


# ===========================================================================
# P11B5-12 / P11B5-13 — flow_panel kart künyeleri + CF çelişkisi
# ===========================================================================

class TestP11B512SurtunmeKunyesi:

    @node_gerekli
    def test_olculmus_ile_sabit_ayni_kart_degil(self, tmp_path):
        src = oku('hrma/static/js/panels/flow_panel.js')
        betik = (kes_fonksiyon(src, 'frictionKind')
                 + kes_fonksiyon(src, 'frictionOriginText')
                 + '\nconsole.log(JSON.stringify({\n'
                   '  olculmus: frictionKind('
                   '{friction_loss_fraction_source:"integral_bl_measured"}),\n'
                   '  sabit: frictionKind('
                   '{friction_loss_fraction_source:"legacy_constant"}),\n'
                   '  beyansiz: frictionKind({}),\n'
                   '  metin: frictionOriginText({}),\n'
                   '}));\n')
        out = node_kos(tmp_path, betik)
        assert out['olculmus'] != out['sabit'], (
            'ölçülmüş sürtünme kaybı ile sabit yedek AYNI kartı alıyor — '
            'kullanıcı sayının kazanılıp kazanılmadığını göremez')
        assert out['olculmus'] == 'ok' and out['sabit'] == 'warn'
        assert out['beyansiz'] == 'dim'
        assert 'not declared' in out['metin']


class TestP11B513ItkiTanimiVeCFCeliskisi:

    @node_gerekli
    def test_thrust_karti_hangi_itki_oldugunu_soyler(self, tmp_path):
        src = oku('hrma/static/js/panels/flow_panel.js')
        betik = ('const U = { fmt: (v, d) => Number(v).toFixed(d) };\n'
                 + kes_fonksiyon(src, 'thrustDefinitionText')
                 + '\nconsole.log(JSON.stringify({metin:'
                   ' thrustDefinitionText({thrust_N: 1000,'
                   ' thrust_full_flow_N: 4430}, {thrust_effective_N: 950})}));\n')
        out = node_kos(tmp_path, betik)
        assert 'performance.thrust_N' in out['metin'], (
            'THRUST kartı hangi itki tanımını gösterdiğini söylemiyor')
        assert '4.430' in out['metin'], 'kardeş tanımın oranı yazılmıyor'
        assert '0.950' in out['metin']

    @node_gerekli
    def test_cf_ideali_asinca_rozet_cikar(self, tmp_path):
        src = oku('hrma/static/js/panels/flow_panel.js')
        betik = ('const U = { fmt: (v, d) => Number(v).toFixed(d),\n'
                 '  badge: (t, k, tip) => JSON.stringify({t, k, tip}) };\n'
                 'function T(k, f) { return f; }\n'
                 + kes_fonksiyon(src, 'cfContradictionBadge')
                 + '\nconsole.log(JSON.stringify({\n'
                   '  celiskili: cfContradictionBadge({CF:1.9, CF_ideal:1.7}),\n'
                   '  tutarli: cfContradictionBadge({CF:1.5, CF_ideal:1.7}),\n'
                   '  eksik: cfContradictionBadge({CF:1.9}),\n'
                   '}));\n')
        out = node_kos(tmp_path, betik)
        assert out['celiskili'], (
            'CF > CF_IDEAL çelişkisi rozetsiz geçiyor: kayıpsız üst sınırı '
            'aşan bir itki katsayısı sessizce basılıyor')
        assert 'CF > CF_IDEAL' in out['celiskili']
        assert out['tutarli'] == '', 'aşırı düzeltme: tutarlı koşumda rozet var'
        assert out['eksik'] == '', 'alan yokken hüküm veriliyor'


# ===========================================================================
# P11B5-15 — limitsiz malzemede YEŞİL hüküm yok + ablatif astar süzgeci
# ===========================================================================

class TestP11B515AstarHukmu:

    @node_gerekli
    def test_limit_yoksa_yesil_hukum_verilmez(self, tmp_path):
        src = oku('hrma/static/js/panels/cooling_panel.js')
        alanlar = re.search(r'const WALL_LIMIT_FIELDS = \[(.*?)\];', src, re.S)
        assert alanlar, 'limit alanları tek kaynakta değil'
        betik = ('const WALL_LIMIT_FIELDS = [%s];\n' % alanlar.group(1)
                 + kes_fonksiyon(src, 'wallLimitsResolved')
                 + kes_fonksiyon(src, 'wallKind')
                 + '\nconsole.log(JSON.stringify({\n'
                   '  ablatif: wallKind({max_wall_hot_K: 3249.6}),\n'
                   '  eriyen: wallKind({max_wall_hot_K: 3249.6,'
                   ' material_melting_K: 1356}),\n'
                   '  saglam: wallKind({max_wall_hot_K: 700,'
                   ' material_service_limit_K: 900}),\n'
                   '  sicaklikyok: wallKind({}),\n'
                   '}));\n')
        out = node_kos(tmp_path, betik)
        assert out['ablatif'] != 'ok', (
            'kıyaslanacak HİÇBİR limit yayımlanmamışken panel 3.249,6 K '
            'cidarda YEŞİL "WALL WITHIN LIMIT" hükmü veriyor — hüküm '
            'kazanılmadan yayımlanıyor (fail-open)')
        assert out['ablatif'] == 'dim'
        assert out['eriyen'] == 'err', 'aşırı düzeltme: erime hükmü kayboldu'
        assert out['saglam'] == 'ok', 'aşırı düzeltme: sağlam koşum griye düştü'
        assert out['sicaklikyok'] == 'dim'

    def test_limitsiz_rozet_gerekcesiyle_basilir(self):
        js = oku('hrma/static/js/panels/cooling_panel.js')
        assert 'panel.regen.wallNoLimit' in js
        assert 'WALL LIMIT NOT PUBLISHED' in js

    @node_gerekli
    def test_ablatif_astar_seciciden_cikar(self, tmp_path):
        src = oku('hrma/static/js/panels/cooling_panel.js')
        etiket = re.search(r"const NON_REGEN_TAG = '([a-z_]+)';", src)
        assert etiket and etiket.group(1) == 'ablative'
        betik = ("const NON_REGEN_TAG = '%s';\n" % etiket.group(1)
                 + kes_fonksiyon(src, 'ablatifAnahtarlar')
                 + '\nconst H = { list: () => ([\n'
                   "  {key:'ablative', tags:['ablative','liner']},\n"
                   "  {key:'copper', tags:['liner','shell']},\n"
                   "  {key:'cucrzr', tags:['liner']},\n"
                   ']) };\n'
                   'console.log(JSON.stringify(ablatifAnahtarlar(H)));\n')
        out = node_kos(tmp_path, betik)
        assert out.get('ablative') is True, (
            'ablatif astar rejeneratif KANAL malzemesi olarak sunulmaya '
            'devam ediyor — panelin modeli o malzeme için tanımsız')
        assert 'copper' not in out and 'cucrzr' not in out, (
            'aşırı düzeltme: gerçek astar malzemeleri de eleniyor')


# ===========================================================================
# P11B5-16 — blowdown.* sözlük ailesi (ürün onarımı aynı kulvarın önceki
# aşamasında indi; bu bekçi onu yerinde tutar)
# ===========================================================================

class TestP11B516BlowdownSozlugu:

    def test_kullanilan_her_anahtar_iki_dilde_tanimli(self):
        bp = oku('hrma/static/js/blowdown_panel.js')
        i18n = oku('hrma/static/js/i18n_common.js')
        kullanilan = sorted(set(
            re.findall(r"T\(\s*'(blowdown\.[A-Za-z0-9_.]+)'", bp)
            + re.findall(r"TF\(\s*'(blowdown\.[A-Za-z0-9_.]+)'", bp)
            + re.findall(r'data-i18n="(blowdown\.[A-Za-z0-9_.]+)"', bp)))
        assert len(kullanilan) >= 18
        eksik = [k for k in kullanilan if ("'%s':" % k) not in i18n]
        assert not eksik, (
            'blowdown paneli sözlükte olmayan anahtar kullanıyor; TR '
            'arayüzde panel İngilizce kalır: %s' % eksik)
        # Anahtar EN ve TR bloklarının İKİSİNDE de olmalı (dosya sonuna
        # atılmış tek blok yetmez).
        tr_bas = i18n.index('\n        tr: {')
        tek_dilli = [k for k in kullanilan
                     if ("'%s':" % k) not in i18n[:tr_bas]
                     or ("'%s':" % k) not in i18n[tr_bas:]]
        assert not tek_dilli, (
            'anahtar yalnız tek dil bloğunda: %s' % tek_dilli)


# ===========================================================================
# P11B5-17 — rozet α_max ile çizilen tepe ayrışması ilan edilir
# ===========================================================================

class TestP11B517AlfaAyrismasi:

    @node_gerekli
    def test_ayrisma_sayiyla_ilan_edilir(self, tmp_path):
        src = oku('hrma/static/js/sixdof_panel.js')
        sabitler = ''.join(
            'const %s = %s;\n' % (ad, deger)
            for ad, deger in re.findall(
                r'^    const ([A-Z][A-Z0-9_]*)\s*=\s*([0-9.eE+-]+);',
                src, re.M))
        betik = (sabitler
                 + 'function T(k, f) { return f; }\n'
                   'function TF(k, p, f) { return f; }\n'
                 + kes_fonksiyon(src, '_buildAlphaFigure')
                 + '\n// rozet 2,00°, çizilen tepe 1,88° → %6 ayrışma\n'
                   'const ser = {time:[1,2,3,4], alpha_deg:[0.5,1.88,1.2,0.4],\n'
                   '  speed:[100,100,100,100]};\n'
                   'const fig = _buildAlphaFigure(ser,\n'
                   '  {max_speed:100, apogee_time:9, max_alpha_deg:2.0});\n'
                   'const ayni = _buildAlphaFigure(ser,\n'
                   '  {max_speed:100, apogee_time:9, max_alpha_deg:1.88});\n'
                   'console.log(JSON.stringify({\n'
                   '  d: fig.badgePlotDivergence, note: fig.note,\n'
                   '  ayni: ayni.badgePlotDivergence}));\n')
        out = node_kos(tmp_path, betik)
        assert out['d'] and out['d']['diverges'] is True, (
            'rozetin α_max değeri ile çizilen eğrinin tepesi ayrıştığı '
            'hâlde panel susuyor: kesikli çizgi eğrinin üstünde havada '
            'kalıyor ve kullanıcı grafikte olmayan bir tepe okuyor')
        assert abs(out['d']['rel'] - (0.12 / 2.0)) < 1e-9
        assert 'NOT a point of the drawn curve' in (out['note'] or '')
        assert out['ayni']['diverges'] is False, (
            'aşırı düzeltme: iki sayı aynıyken de ayrışma ilan ediliyor')


# ===========================================================================
# P11S1-02 — UNSAFE hükmünün görsel imzası doğar
# ===========================================================================

class TestP11S102DurumPili:

    def test_durum_pili_urun_kodunda_tuketilir(self):
        js = oku('hrma/static/js/app.js')
        assert 'hd-statustag' in js, (
            'results_hud.css durum pilini tanımlıyor ama ürün kodunda '
            'tüketicisi yok: UNSAFE hükmünün pil imzası hiç doğmuyor')
        assert 'hd-state-word' in js, 'P17B2-01 sözcük sözleşmesi kayboldu'

    def test_led_dugumu_kartin_icinde(self):
        js = oku('hrma/static/js/app.js')
        assert '<span class="hd-led"></span>' in js, (
            '`.hd-led` düğümü kartta yok — [data-state="unsafe"] .hd-led '
            'yanıp sönme kuralı (UNSAFE\'in tek kalıcı görsel imzası) '
            'hiçbir zaman uygulanmıyor')
        # LED, durum sözcüğünün pilinin İÇİNDE olmalı: bindState kartın
        # kendisine data-state koyar, kural ata-torun seçicisidir.
        i_pil = js.index('hd-statustag hd-state-word')
        i_led = js.index('<span class="hd-led"></span>')
        assert i_pil < i_led < i_pil + 400

    def test_css_kurallari_yerinde(self):
        css = oku('hrma/static/css/results_hud.css')
        assert '.hd-statustag {' in css
        assert '[data-state="unsafe"] .hd-led' in css


# ===========================================================================
# P11S1-05 — bağlama haritası kapsam sınırını beyan eder
# ===========================================================================

class TestP11S105KapsamBeyani:

    def test_beyan_uclari_ve_disarida_kalani_sayar(self):
        import sys
        if str(KOK) not in sys.path:
            sys.path.insert(0, str(KOK))
        import tools.wiring_map as w
        metin = w.kapsam_beyani()
        assert 'KAPSAM SINIRI' in metin
        for uc in ('/calculate', '/calculate_solid', '/calculate_liquid'):
            assert uc in metin
        assert 'YOKTUR' in metin, (
            'harita kapsam dışında kalan uçları söylemiyor: başlığı '
            '"HRMA bağlama haritası" olan belge ürünün tamamını gördüğünü '
            'ima ediyor')
        assert '--uclar' in metin, 'okuyucuya geniş kapsam yolu gösterilmiyor'

    def test_beyan_ciktiya_basilir(self):
        py = oku('tools/wiring_map.py')
        assert py.count('data-kapsam="1"') == 2, (
            'kapsam beyanı hem sayfa hem dizin başlığında olmalı')
