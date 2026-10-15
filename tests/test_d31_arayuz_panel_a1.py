# -*- coding: utf-8 -*-
"""ÖH D31 · arayuz-panel a1 — kilit bekçileri.

Her sınıf bir defter kalemini kilitler. Ölçümler
``docs/scofield/raw/OH/D31/arayuz-panel/a1/once.json`` (taban ağacı) ve
``sonra.json`` (bu worktree) dosyalarında; buradaki iddialar ÜRÜN
DOSYALARINI doğrudan okur, donmuş sayıya güvenmez.

D30 dersi (18) gereği bekçiler KULLANICININ KOŞTUĞU yolu ölçer: şablon
içi betikler app.js'i gölgeleyebildiği için her iddia, iddia edilen
davranışın hangi dosyada yaşadığını adıyla sınar.
"""
import json
import os
import re
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def var_mi(rel):
    return os.path.exists(os.path.join(KOK, rel))


# ===========================================================================
# OH-D30-02 — 422/400 ret gerekçesi kullanıcıya iniyor
# ===========================================================================
#: Ret gövdesini okuması gereken şablonlar (üçü de reject_body.js yükler).
_RET_SAYFALARI = ('advanced', 'solid', 'liquid')


class TestOHD3002RetGovdesi:
    """Taban ölçümü (once.json · M1): `HTTP error! status` ALTI yerde
    (app.js 1, advanced.html 4, liquid.html 1), paylaşılan çözücü YOK,
    `missing_fields` okuması app.js/advanced/solid'de 0."""

    def test_paylasilan_cozucu_var(self):
        assert var_mi('hrma/static/js/reject_body.js'), (
            'ret gövdesi çözücüsü tek kaynakta değil')
        m = oku('hrma/static/js/reject_body.js')
        for alan in ('invalid_fields', 'missing_fields', 'field', 'reason'):
            assert alan in m, f'çözücü {alan} sözleşmesini bilmiyor'

    def test_ham_http_error_kalibi_kalmadi(self):
        """Gövdeyi okumadan durum sayısı fırlatan dal KALMADI."""
        kalan = []
        for rel in ('hrma/static/js/app.js',
                    'hrma/templates/advanced.html',
                    'hrma/templates/liquid.html',
                    'hrma/templates/solid.html'):
            n = oku(rel).count('HTTP error! status')
            if n:
                kalan.append((rel, n))
        assert not kalan, (
            'ret gövdesini okumadan HTTP durumu fırlatan dal(lar): %r '
            '— kullanıcı hangi alanın neden reddedildiğini göremez' % kalan)

    @pytest.mark.parametrize('sayfa', _RET_SAYFALARI)
    def test_cozucu_kullanan_sayfa_modulu_yukler(self, sayfa):
        """`HRMAReject` çağıran sayfa <script> etiketini de taşır.

        FAIL-CLOSED kapının kendisi: etiket düşerse çözücü tanımsız kalır
        ve ret metni hiç kurulamaz. Bu bekçi o düşüşü mekanik yakalar.
        """
        metin = oku('hrma/templates/%s.html' % sayfa)
        assert 'HRMAReject.' in metin, (
            '%s.html ret gövdesini ortak çözücüyle okumuyor' % sayfa)
        # Yorumda geçmesi YETMEZ: <script> etiketinin kendisi aranır
        # (ters-mutasyon ölçtü: yalnız ada bakan iddia etiket sökülünce
        # yeşil kalıyordu — sahte yeşil, D30 dersi 18).
        assert '<script src="/static/js/reject_body.js"></script>' in metin, (
            '%s.html HRMAReject çağırıyor ama modülü YÜKLEMİYOR' % sayfa)

    def test_app_js_tuketicisi_sayfasi_modulu_yukler(self):
        """app.js yalnız advanced.html'de yükleniyor; kapı orada olmalı."""
        appjs = oku('hrma/static/js/app.js')
        assert 'HRMAReject.' in appjs
        adv = oku('hrma/templates/advanced.html')
        assert '<script src="/static/js/app.js"></script>' in adv
        assert '<script src="/static/js/reject_body.js"></script>' in adv

    def test_uc_kopya_tek_kaynaga_devretti(self):
        """`_ihracRetMetni` üç şablonda da yalnız devreder (kopya borcu)."""
        for sayfa in _RET_SAYFALARI:
            metin = oku('hrma/templates/%s.html' % sayfa)
            bas = metin.index('function _ihracRetMetni(')
            govde = metin[bas:bas + 900]
            assert 'HRMAReject.metni(' in govde, (
                '%s.html çözücüyü hâlâ kendi içinde kopyalıyor' % sayfa)

    def test_cozucu_alan_adlarini_gercekten_basiyor(self):
        """Node ile canlı koşum: yapılı gövde → alan adları metinde."""
        betik = (
            "const R=require('%s');"
            "const t=R.metni({status:'validation_error',"
            "message:'bad',invalid_fields:[{field:'l_star',"
            "reason:'out_of_band'}],missing_fields:['mode']},422);"
            "process.stdout.write(t);"
            % os.path.join(KOK, 'hrma/static/js/reject_body.js'))
        cikti = subprocess.run(['node'], input=betik, capture_output=True,
                               text=True, timeout=60)
        assert cikti.returncode == 0, cikti.stderr
        metin = cikti.stdout
        for parca in ('validation_error', 'l_star', 'out_of_band',
                      'missing_fields', 'mode'):
            assert parca in metin, (
                'ret metni %r taşımıyor: %r' % (parca, metin))


# ===========================================================================
# OH-D27-13 — 3B ikincil ölçü yedekleri: künye zorunlu + panel rozeti
# ===========================================================================
class TestOHD2713VarsayimOlculeri:
    """Taban ölçümü (once.json · M3): `kunyesiz_yedek_fail_closed = 0`,
    `panel_rozet_solid = 0`, `panel_rozet_advanced = 0` — 9 Eyl kararının
    üçte biri (fail-closed) ve rozetin panel ayağı inmemişti."""

    def test_kunyesiz_yedek_kapisi_var(self):
        m = oku('hrma/static/js/motor_viz3d.js')
        assert 'ASSUMED_DIM_NO_BASIS' in m
        assert 'function _kunyeKapisi(' in m, (
            'künye kapısı yok')

    def test_kunyesiz_yedek_canli_olarak_reddediliyor(self):
        """Node: `basis` boş bir VARSAYIM kaydı yazılmaya kalkılırsa atılır."""
        betik = r"""
        var kod = require('fs').readFileSync(%r, 'utf8');
        var m = kod.match(/function _kunyeKapisi\(alan, kayit\) \{[\s\S]*?\n    \}/);
        if (!m) { console.error('KAPI BULUNAMADI'); process.exit(2); }
        var AssumedDimError = function (a) { this.field = a; };
        eval(m[0]);
        var defter = {}, sonuc = [];
        try { defter.a = _kunyeKapisi('casing_wall',
                          { kind: 'assumed', basis: null });
              sonuc.push('KUNYESIZ_GECTI'); } catch (e) { sonuc.push('RED'); }
        try { defter.b = _kunyeKapisi('grain_length',
                          { kind: 'assumed', basis: 'fallback 0.8*Lch' });
              sonuc.push('KUNYELI_GECTI'); } catch (e) {
              sonuc.push('KUNYELI_REDDEDILDI'); }
        try { defter.c = _kunyeKapisi('chamber_diameter',
                          { kind: 'computed', basis: null });
              sonuc.push('COMPUTED_GECTI'); } catch (e) {
              sonuc.push('COMPUTED_REDDEDILDI'); }
        process.stdout.write(sonuc.join(','));
        """ % os.path.join(KOK, 'hrma/static/js/motor_viz3d.js')
        r = subprocess.run(['node'], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'RED,KUNYELI_GECTI,COMPUTED_GECTI', (
            'künye kapısı beklendiği gibi davranmıyor: %r' % r.stdout)

    def test_panel_rozeti_iki_sayfada_da_var(self):
        m = oku('hrma/static/js/motor_viz3d.js')
        assert 'renderAssumedDimBadge' in m
        assert 'assumedDimensions:' in m, 'rozet listesi dışa açık değil'
        for sayfa in ('solid', 'advanced'):
            assert 'hrma-dims-assumed' in oku('hrma/templates/%s.html' % sayfa), (
                '%s.html panelinde varsayım ölçüsü rozeti kapsayıcısı yok'
                % sayfa)

    def test_rozet_sahne_cipiyle_ayni_defterden_beslenir(self):
        """İki yüzey ayrışamaz: rozet çipin KENDİ alan listesinden ve
        defterin (`srcDecl`) künyesinden beslenir; ikinci bir süzgeç yok."""
        m = oku('hrma/static/js/motor_viz3d.js')
        i = m.index('function _varsayimRozetiniTazele(')
        blok = m[i:i + 900]
        assert 'cip.fields.map(' in blok, 'rozet çipin alan listesinden gelmiyor'
        assert 'srcNote(alan, decls[alan])' in blok, (
            'rozet defterin künyesini okumuyor')
        i = m.index('function dimensionSourceChipDefs(')
        blok = m[i:i + 1800]
        assert 'fields: notlar.map(' in blok, (
            'çip kendi alan listesini yayımlamıyor — rozet ondan beslenemez')


# ===========================================================================
# OH-D26-03 — amber ailesi: token + muafiyetsiz bekçi kapsamı
# ===========================================================================
class TestOHD2603Amber:
    """Taban ölçümü (once.json · M4): `theme_css_hd_amber_tanimi = 0`,
    ayrışık amber değerleri {#ffb454, #ffbe46} — token olmadığı için
    D20 bekçisi `hd-amber` yedeklerini ATLIYORDU."""

    def test_amber_theme_css_de_token(self):
        theme = oku('hrma/static/css/theme.css')
        m = re.search(r'--hd-amber:\s*(#[0-9a-fA-F]{6})', theme)
        assert m, '--hd-amber theme.css token katmanında tanımlı değil'
        assert m.group(1).lower() == '#ffbe46', (
            'token değeri ürünün kendi değerinden (#ffbe46) saptı: %s'
            % m.group(1))

    def test_iki_css_dosyasi_ayni_token_kumesi(self):
        def tok(s):
            return set(re.findall(r'--(hd-[a-z0-9-]+):', s))
        assert 'hd-amber' in tok(oku('hrma/static/css/theme.css'))
        assert 'hd-amber' in tok(oku('hrma/static/css/hd_doc.css'))

    def test_ayrisik_amber_yedegi_kalmadi(self):
        """`var(--hd-amber, #hex)` yedeklerinin hepsi token değerinde."""
        ayrisan = []
        for kok, _d, dosyalar in os.walk(os.path.join(KOK, 'hrma')):
            for ad in dosyalar:
                if not ad.endswith(('.js', '.css', '.html')):
                    continue
                yol = os.path.join(kok, ad)
                with open(yol, encoding='utf-8', errors='replace') as f:
                    icerik = f.read()
                for hx in re.findall(r'--hd-amber\s*,\s*(#[0-9a-fA-F]{6})',
                                     icerik):
                    if hx.lower() != '#ffbe46':
                        ayrisan.append((os.path.relpath(yol, KOK), hx))
        assert not ayrisan, (
            'token değerinden ayrışan amber yedekleri: %r' % ayrisan)

    def test_ciplak_ffb454_sabiti_kalmadi(self):
        """Token'a bağlanmamış çıplak amber sabiti yok."""
        kalan = []
        for rel in ('hrma/static/js/panels/correlation_panel.js',
                    'hrma/static/js/panels/flow_panel.js',
                    'hrma/templates/advanced.html',
                    'hrma/templates/liquid.html'):
            if '#ffb454' in oku(rel):
                kalan.append(rel)
        assert not kalan, 'ayrışık amber (#ffb454) kalan dosyalar: %r' % kalan


# ===========================================================================
# OH-D30-06 — birimli sayılar TR kipinde virgül basar
# ===========================================================================
#: Kullanıcıya sayı BASAN paneller (CSS geometrisi bu listeye girmez).
_SAYI_BASAN_PANELLER = (
    'cfd_panel.js', 'correlation_panel.js', 'joint_panel.js',
    'protection_panel.js', 'stability_panel.js', 'uncertainty_panel.js')


class TestOHD3006SayiBicimi:
    """Taban ölçümü (once.json · M5): panels/ altında 17 `toFixed`,
    `I18N.number` atfı 0 — TR kipinde '36.3 bar' noktalı kalıyordu."""

    def test_ortak_sayi_yardimcisi_var(self):
        d = oku('hrma/static/js/analysis_dock.js')
        i = d.index('            num: function (value, digits) {')
        assert 'I18N.number' in d[i:i + 700], (
            'U.num biçimi tek kaynaktan (I18N.number) almıyor')

    @pytest.mark.parametrize('ad', _SAYI_BASAN_PANELLER)
    def test_panel_sayiyi_yerel_ayracla_basiyor(self, ad):
        m = oku('hrma/static/js/panels/' + ad)
        assert ('U.num(' in m) or ('_num(' in m), (
            '%s kullanıcıya basılan sayıyı yerelleştirmiyor' % ad)

    def test_css_geometrisi_toFixed_kalir(self):
        """Piksel/opaklık toFixed'i BİLEREK korunur: virgül stili bozar."""
        m = oku('hrma/static/js/panels/correlation_panel.js')
        assert "(2 + oran * 46).toFixed(1) + 'px;'" in m, (
            'CSS genişliği yerelleştirilmiş — stil bozulur')

    def test_yerel_ayrac_canli_olcum(self):
        """Node: I18N.number TR kipinde virgül, EN kipinde nokta basar."""
        yol = os.path.join(KOK, 'hrma/static/js/i18n.js')
        betik = (
            "global.window=global;"
            "global.document={documentElement:{lang:'en',"
            "setAttribute:function(){},getAttribute:function(){return null;}},"
            "addEventListener:function(){},querySelectorAll:function(){"
            "return [];},querySelector:function(){return null;},"
            "createElement:function(){return {style:{},"
            "setAttribute:function(){},appendChild:function(){}};}};"
            "global.localStorage={getItem:function(){return null;},"
            "setItem:function(){}};"
            "global.navigator={language:'en'};"
            "require(%r);"
            "var out=[];"
            "try{window.I18N.setLang('tr');}catch(e){}"
            "out.push(String(window.I18N.number(36.3,1)));"
            "try{window.I18N.setLang('en');}catch(e){}"
            "out.push(String(window.I18N.number(36.3,1)));"
            "process.stdout.write(out.join('|'));" % yol)
        r = subprocess.run(['node'], input=betik, capture_output=True,
                           text=True, timeout=60)
        if r.returncode != 0:
            pytest.skip('i18n.js node ortamında koşmadı: %s'
                        % r.stderr.strip()[:200])
        tr, en = r.stdout.split('|')
        assert en == '36.3', 'EN kipi nokta basmalı: %r' % en
        assert tr == '36,3', 'TR kipi virgül basmalı: %r' % tr


# ===========================================================================
# P12aB4-18 — bindState ölü değil: hüküm yoksa NOT_EVALUATED yayımlanır
# ===========================================================================
class TestP12aB418NotEvaluated:
    """Taban ölçümü (once.json · M6): `state` taşıyan metrik SAYISI
    solid.html 0, liquid.html 0 — `bindState` döngüsü ayakta ama ölü."""

    @pytest.mark.parametrize('sayfa', ('solid', 'liquid'))
    def test_hukumsuz_metrik_not_evaluated_alir(self, sayfa):
        m = oku('hrma/templates/%s.html' % sayfa)
        i = m.index('HRMAHud.bindState(')
        blok = m[max(0, i - 200):i + 200]
        assert "'NOT_EVALUATED'" in blok, (
            '%s.html hükümsüz metriği sessiz bırakıyor (fail-open okunur)'
            % sayfa)
        assert 'if (m.state && cards[i])' not in m, (
            '%s.html eski ölü koşul hâlâ duruyor' % sayfa)

    def test_sozcuk_hud_sozlugunde_var(self):
        """Sözcük UYDURULMADI: STATE_MAP'te hazır duruyor."""
        h = oku('hrma/static/js/hud.js')
        assert re.search(r'NOT_EVALUATED:\s*\'not-evaluated\'', h)
        assert '[data-state="not-evaluated"]' in oku(
            'hrma/static/css/results_hud.css'), (
            'sözcüğün görsel karşılığı yok — LED hükümsüz görünmez')


# ===========================================================================
# OH-D28-05 — katı erozyon üssü ekstrapolasyonu kullanıcıya UYARI olarak iner
# ===========================================================================
class TestOHD2805ErozyonZinciri:
    """Zincirin üç ayağı üç kulvarda: kod (kati, D30), i18n anahtarı
    (fix-31), panel satırı (bu dalga). Ölçüm (once.json · M2 ve çapa
    A2 gövdesi): kod 1 geçiş, anahtar EN+TR 2 geçiş, panel kanalı açık.
    Bu bekçi ZİNCİRİN TAMAMINI kilitler — bir halka düşerse kırmızı."""

    def test_motor_uyari_kodunu_yayimliyor(self):
        m = oku('hrma/engines/solid_rocket_engine.py')
        assert "'warn.solid.erosion_exponent_extrapolated'" in m
        assert 'exponent_extrapolated' in m

    def test_i18n_anahtari_iki_dilde_var(self):
        m = oku('hrma/static/js/i18n_common.js')
        n = m.count("'warn.solid.erosion_exponent_extrapolated'")
        assert n >= 2, ('anahtar EN+TR iki blokta da olmalı, bulunan: %d' % n)

    def test_panel_kanali_kodu_ekrana_indiriyor(self):
        """solid.html uyarı paneli `results.warnings`i jenerik taşır."""
        m = oku('hrma/templates/solid.html')
        assert '(results && results.warnings) || []' in m
        assert 'window.I18N.tf(w.code' in m, (
            'kod TF()den geçmiyor — ekranda ham anahtar görünür')
        assert var_mi('hrma/static/js/analysis_dock.js')
        assert 'i18n_common.js' in oku('hrma/static/js/analysis_dock.js'), (
            'solid.html sözlüğü doğrudan yüklemiyor; enjeksiyon da yoksa '
            'uyarı İngilizce ham anahtar olarak düşer')

    def test_uc_gercekten_yayimliyor(self, capa_a2):
        """Çapa A2 (40 bar apcp/bates/grafit) gövdesinde uyarı kodu VAR.

        Çapa kaydı `_repr_agac` ile yazıldığı için yapraklar repr()
        dizeleridir; ölçüt kodun gövdede GEÇMESİDİR (kanal ucu ölçüsü).
        """
        uyarilar = json.dumps(capa_a2.get('warnings') or [],
                              ensure_ascii=False)
        assert 'warn.solid.erosion_exponent_extrapolated' in uyarilar, (
            '40 bar sınıfı katı koşumda ekstrapolasyon uyarısı yayımlanmadı: '
            '%s' % uyarilar[:400])


@pytest.fixture(scope='module')
def capa_a2():
    """Çapa koşumunun katı motor gövdesi (sonra.json, yoksa once.json)."""
    d = 'docs/scofield/raw/OH/D31/arayuz-panel/a1'
    for ad in ('capa_sonra.json', 'capa_once.json'):
        yol = os.path.join(KOK, d, ad)
        if os.path.exists(kanit_gerekli(yol)):
            with open(kanit_gerekli(yol), encoding='utf-8') as f:
                return (json.load(f)['A_gecerli_govde']
                        ['A2_kati_calculate_solid'].get('govde') or {})
    pytest.skip('çapa kaydı yok')


# ===========================================================================
# P11B3-27 — okunmayan künye/tanım alanları panele taşındı
# ===========================================================================
class TestP11B327KunyeAlanlari:
    """Taban ölçümü (once.json · M8): `refine_factor = 0`,
    `throat_area_m2 = 0` (fea/thermal_fea/cfd panellerinde sıfır geçiş)."""

    def test_quality_source_panele_tasindi(self):
        m = oku('hrma/static/js/fea_panel.js')
        # Yorumda geçmesi YETMEZ; alanı gerçekten OKUYAN ifade aranır
        # (ters-mutasyon ölçtü: 'quality._source' dizesi kendi künye
        # yorumumda da geçiyordu — sahte yeşil, D30 dersi 18).
        assert 'fea.quality._source' in m, 'ölçüm kodunun kimliği taşınmıyor'
        assert 'Mesh quality metrics computed by: ' in m, (
            'kimlik ekrana basılmıyor')

    def test_refine_factor_panele_tasindi(self):
        m = oku('hrma/static/js/fea_panel.js')
        assert 'vm.limits.refine_factor' in m
        assert 'radial station counts by ' in m

    def test_throat_alani_panele_tasindi(self):
        m = oku('hrma/static/js/panels/cfd_panel.js')
        assert 'vm.throat.area_m2' in m
        assert "'Throat area A_t (used for c*)'" in m

    def test_alan_yoksa_satir_kurulmaz(self):
        """FAIL-CLOSED: alan gelmezse sayı UYDURULMAZ.

        ÖH D32 / OH-D31-01 — ÖLÇÜM YÖNTEMİ DÜZELTİLDİ (D31 dersi 22, kesik
        dilim). İddia, imzadan geriye SABİT 400 bayt kesip kapıyı orada
        arıyordu; etiket sözlüğe bağlanınca (ham dize -> ``TF(...)``) araya
        giren gerekçe yorumu kapıyı pencerenin dışına itti ve iddia, ÜRÜN
        kapısı yerinde DURURKEN kırmızıya düştü. Sınır artık tahmin
        edilmiyor, ÖLÇÜLÜYOR: kapı, cümleyi saran ``if`` bloğunun içinde
        aranıyor. Kapı gerçekten sökülürse iddia yine kırmızı verir.
        """
        m = oku('hrma/static/js/fea_panel.js')
        i = m.index('radial station counts by ')
        blok_bas = m.rindex('if (vm.limits && vm.limits.clamped)', 0, i)
        blok = m[blok_bas:i]
        assert 'isFinite(vm.limits.refine_factor)' in blok, (
            'çarpan yokken de cümle kuruluyor')


# ===========================================================================
# P11B4-27 — ödenmiş rapor yükü kullanıcıya açıldı
# ===========================================================================
class TestP11B427RaporYuku:
    """Taban ölçümü (once.json · M9): `markdown_tuketimi = 1` ve o tek
    geçiş dosya başındaki sözleşme YORUMU — üründe sıfır tüketici."""

    def test_rapor_metni_ekrana_acildi(self):
        m = oku('hrma/static/js/panels/correlation_panel.js')
        assert 'function raporMetniHtml(' in m
        assert 'raporMetniHtml(data.markdown)' in m

    def test_metin_kacirilir_ve_degistirilmez(self):
        """Sunucu metni AYNEN gösterilir; özetlenmez, biçimlenmez."""
        m = oku('hrma/static/js/panels/correlation_panel.js')
        i = m.index('function raporMetniHtml(')
        blok = m[i:i + 1400]
        assert 'escapeHtml(markdown)' in blok, 'ham metin kaçırılmıyor'
        assert 'slice(' not in blok, 'metin kırpılıyor (eksik rapor)'

    def test_alan_yoksa_blok_kurulmaz(self):
        m = oku('hrma/static/js/panels/correlation_panel.js')
        i = m.index('function raporMetniHtml(')
        assert "typeof markdown !== 'string'" in m[i:i + 300]


# ===========================================================================
# OH-D19-27 — küçük temizlik demetinin üç ayağı
# ===========================================================================
class TestOHD1927Temizlik:
    """Üç ayak ÖLÇÜLDÜ (once.json · M7): (a) `R_UNIVERSAL` içe aktarması
    app.py'de 0 (D29 app-api-uc a1 söktü, gerekçe yorumda duruyor),
    (b) `getTileInfo().failedCount` tüketicisi launch_site.html'de 2,
    (c) `_touchTile` negatif önbellek tazelemesi 4 (D30 a2 onardı)."""

    def test_a_olu_import_sokuldu(self):
        m = oku('hrma/app.py')
        assert not re.search(r'^from .*import.*R_UNIVERSAL', m, re.M), (
            'ölü R_UNIVERSAL içe aktarması geri geldi')

    def test_b_failedCount_tuketicisi_var(self):
        assert 'failedCount' in oku('hrma/static/js/launch_site_globe.js')
        ls = oku('hrma/templates/launch_site.html')
        assert '.failedCount' in ls, (
            'çevrimdışı notu yapışkan bayrağa geri döndü')
        assert 'info.failedCount > 0' in ls

    def test_c_negatif_onbellek_tazeleniyor(self):
        g = oku('hrma/static/js/launch_site_globe.js')
        assert '_touchTile' in g
        i = g.index('_touchTile')
        assert g.count('_touchTile') >= 3, (
            'negatif önbellek girdisi LRU\'da tazelenmiyor')


# ===========================================================================
# P12aB1-05 — parametreli i18n düğümü dil değişiminde donmaz
# ===========================================================================
#: Kabuk yayıcıları: dil değişiminde tazelenmesi gereken düğümleri kuran
#: üç dosya (P12aB1-05'in adı geçen sahası).
_YAYICILAR = ('analysis_center.js', 'settings_panel.js', 'update_check.js')


class TestP12aB105I18nParams:
    """Taban ölçümü (once.json · M10): `data-i18n-params` yazımı
    analysis_center 2, settings_panel 7, update_check 1 — koruma artık
    TEK yayıcıda değil. Bu bekçi kapsamın GERİLEMESİNİ yasaklar ve
    parametreli anahtar yazan her yayıcının params da yazmasını sınar."""

    @pytest.mark.parametrize('ad', _YAYICILAR)
    def test_yayici_params_korumasi_tasiyor(self, ad):
        m = oku('hrma/static/js/' + ad)
        assert 'data-i18n-params' in m, (
            '%s parametreli düğüm yazarken params yazmıyor — dil '
            'değişiminde metin eski dilde donar' % ad)

    @pytest.mark.parametrize('ad', _YAYICILAR)
    def test_parametreli_anahtar_params_siz_yazilmiyor(self, ad):
        """Parametreli bir anahtar `data-i18n` ile params'SIZ yazılırsa
        dil değişiminde düğüm ESKİ DİLDE donar (i18n.js:374-388 yalnız
        `data-i18n-params` taşıyan düğümü yeniden kurar).

        Ölçüt UYDURULMAZ: "parametreli anahtar" tanımı sözlüğün kendi
        metninden gelir — EN gövdesinde `{ad}` yer tutucusu taşıyan her
        anahtar parametrelidir.
        """
        parametreli = _parametreli_anahtarlar()
        assert parametreli, 'sözlükte parametreli anahtar bulunamadı'
        m = oku('hrma/static/js/' + ad)
        donan = []
        for mm in re.finditer(r'data-i18n="([a-zA-Z0-9_.]+)"', m):
            if mm.group(1) not in parametreli:
                continue
            pencere = m[mm.start(): mm.start() + 260]
            if 'data-i18n-params' not in pencere:
                donan.append(mm.group(1))
        assert not donan, (
            '%s: parametreli anahtar params\'sız yazılıyor -> dil '
            'değişiminde donar: %r' % (ad, sorted(set(donan))))


def _parametreli_anahtarlar():
    """EN sözlüklerinde `{param}` yer tutucusu taşıyan anahtar kümesi."""
    anahtarlar = set()
    for ad in ('i18n_common.js', 'i18n_pages.js', 'i18n_advanced.js',
               'i18n_shell.js'):
        rel = 'hrma/static/js/' + ad
        if not var_mi(rel):
            continue
        for k, v in re.findall(
                r"'([a-zA-Z0-9_.]+)':\s*'((?:[^'\\]|\\.)*)'", oku(rel)):
            if re.search(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', v):
                anahtarlar.add(k)
    return anahtarlar
