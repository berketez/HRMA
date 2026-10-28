"""ÖH Dalga-24 · arayüz · aşama-2 — on bir kalemin bekçileri.

Kapsanan kalemler (ölçüm: ``docs/scofield/raw/OH/D24/arayuz/a2/once.json``
→ ``sonra.json``; ters mutasyon: ``mutasyon.json``):

* **P11B1-02** — ısı efsanesinin sol ucu rampanın tabanını 1,6667 kat
  yanlış etiketliyordu (``fmt(info.qChamber)`` ⟷ ``exp(lnMin)=qC·0,6``).
* **P8B3-23** — "Real-Time" panosunun künyesi altı göstergeye "anlık"
  diyordu; oysa altısı da zamandan bağımsız tasarım noktasıdır.
* **P4B3-27** — ``LAUNCH_SITE_PRESETS`` (14 kayıt, 2'si ``approx``) ürün
  yolunda hiç okunmuyordu; şablon kendi 7 kayıtlık kopyasını taşıyordu.
* **OH-D21-07** — ``/api/database-status`` DENETİMİ patladığında rozet
  "Offline" diyordu: kazanılmamış hüküm (denetlenemedi ≠ kapalı).
* **OH-D23-15** — ``/api/generate-3d`` 500'ü yedek tüketicide sessizce
  yutuluyor, akış "başarıyla üretildi" diyordu.
* **OH-D23-08** — ``solid.html`` üç yanma sınıfını durağan metinle
  sayıyordu; çözücü koşum başına TEK sınıf üretir.
* **OH-D23-20** — cıvata satırında işaretli NET yük görünmüyordu.
* **OH-D17-20** — ``simple.html`` / ``uzaytek.html`` i18n katmanı
  (aşama-1'de onarıldı; GERİLEME bekçisi ÖH D36'da iki sayfayla birlikte
  emekli oldu — Berke 23 Eyl, dalga36/sokum).
* **OH-D19-17** — ``altitude_preview`` çiziminin başlığı eksenleri ters
  söylüyordu (x = irtifa, y = basınç iken "Altitude vs ... Pressure").
* **OH-D20-11** — ``fluxUsage`` yasaklı listeyle çalışıyordu; ``missing``
  türü ``earned:true`` sayılıyordu (fail-open kalıntısı).
* **OH-D21-11** — ``/formulas`` 40.604 px; tur tek karede yakalıyor ve
  Chromium tavanını (16.384 px) aşan bant üst bandın tekrarı oluyordu.

Her bekçi TERS MUTASYONLA doğrulandı: onarım geçici olarak geri
alındığında ilgili test kırmızı yanıyor.
"""
import json
import os
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')
TPL = os.path.join(KOK, 'hrma', 'templates')
ARAC = os.path.join(KOK, 'tools')


def oku(*parcalar):
    with open(os.path.join(*parcalar), encoding='utf-8') as f:
        return f.read()


def sozluk_degeri(metin, anahtar):
    """``'anahtar': '...'`` girdilerinin TÜMÜ (EN + TR)."""
    return re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'",
                      metin)


# =====================================================================
# P11B1-02 — ısı efsanesinin uçları rampanın KENDİ alanıdır
# =====================================================================
class TestP11B102IsiEfsanesi:
    """Efsane bir RENK ⟷ DEĞER sözleşmesidir; ucu kayarsa bant kayar.

    Ölçülen (taban 88a29d3): sol etiket ``fmt(info.qChamber)`` = 2,60
    MW/m², rampanın ``t=0`` ucu ``exp(lnMin) = qC·0,6`` = 1,56 MW/m² —
    sapma 1/0,6 = 1,6667×. Bandın dibinden sayı okuyan kullanıcı akıyı
    %67 fazla okuyordu.
    """

    @pytest.fixture(scope='class')
    def viz3d(self):
        return oku(JS, 'motor_viz3d.js')

    def test_rampa_alani_tek_kaynaktan_okunuyor(self, viz3d):
        assert re.search(r'function\s+heatRampDomain\s*\(', viz3d), (
            'rampa alanını veren tek kaynak fonksiyonu yok')
        # Mesh boyaması da o alandan okur (ikinci kopya yok)
        assert re.search(r'dom\s*=\s*heatRampDomain\(', viz3d)
        assert re.search(r'lnMin\s*=\s*Math\.log\(dom\.qMin\)', viz3d)
        assert re.search(r'lnMax\s*=\s*Math\.log\(dom\.qMax\)', viz3d)

    def test_ramp_alani_dims_heat_uzerinden_yayimlaniyor(self, viz3d):
        assert 'heat.qRampMin' in viz3d and 'heat.qRampMax' in viz3d

    @pytest.mark.parametrize('yol,desen', [
        ('motor_viz_deck.js', r"_hl_min'\)\.textContent\s*=\s*fmt\(info\.qRampMin\)"),
        ('motor_viz_deck.js', r"_hl_max'\)\.textContent\s*=\s*fmt\(info\.qRampMax\)"),
    ])
    def test_guverte_efsanesi_rampa_alanini_basiyor(self, yol, desen):
        assert re.search(desen, oku(JS, yol)), (yol, desen)

    def test_advanced_efsanesi_rampa_alanini_basiyor(self):
        html = oku(TPL, 'advanced.html')
        assert re.search(r"viz_hl_min'\)\.textContent\s*=\s*fmt\(info\.qRampMin\)",
                         html)
        assert re.search(r"viz_hl_max'\)\.textContent\s*=\s*fmt\(info\.qRampMax\)",
                         html)

    def test_qChamber_etiketi_geri_gelmedi(self):
        """Kusurun imzası: efsane etiketine qChamber yazmak."""
        for metin in (oku(JS, 'motor_viz_deck.js'), oku(TPL, 'advanced.html')):
            assert not re.search(r"_hl_min'\)\.textContent\s*=\s*fmt\(info\.qChamber\)",
                                 metin)

    def test_rampa_tabani_sayisal_olarak_qChamberdan_ayrik(self):
        """Sayıyla: taban çarpanı 1 olmadıkça iki uç AYNI DEĞİLDİR.

        Etiketin hangi büyüklüğü gösterdiği bu yüzden önemlidir; çarpan
        1'e çekilirse (rampa tabanı = qC) bu test kendiliğinden düşer ve
        kalem yeniden ölçülür.
        """
        viz3d = oku(JS, 'motor_viz3d.js')
        m = re.search(r'HEAT_RAMP_FLOOR\s*=\s*([0-9.]+)', viz3d)
        assert m, 'rampa taban çarpanı adlandırılmamış'
        floor = float(m.group(1))
        assert 0 < floor <= 1
        qC, qT = 2.60e6, 18.84e6
        rampa_tabani = max(min(qC, qT * 0.9) * floor, 1)
        assert abs(qC / rampa_tabani - 1.0 / floor) < 1e-9
        if floor < 1:
            assert rampa_tabani < qC


# =====================================================================
# P8B3-23 — "Real-Time" panosunun künyesi ad ⟷ davranış çelişkisi
# =====================================================================
class TestP8B323PanoKunyesi:
    """Üst iki sıradaki altı gösterge zamandan BAĞIMSIZ tasarım noktasıdır.

    Panonun kendi künyesi bunu D23'te söylemeye başladı
    (``visualization.py``); arayüz künyesi ("instantaneous" / "anlık")
    hâlâ tersini söylüyordu.
    """

    ANAHTAR = 'chartCap.realtime_dashboard_plot'

    @pytest.fixture(scope='class')
    def kunyeler(self):
        return (sozluk_degeri(oku(JS, 'chart_captions.js'), self.ANAHTAR)
                + sozluk_degeri(oku(JS, 'i18n_common.js'), self.ANAHTAR))

    def test_uc_kunye_de_var(self, kunyeler):
        assert len(kunyeler) == 3, kunyeler

    def test_hicbiri_anlik_demiyor(self, kunyeler):
        for k in kunyeler:
            assert 'instantaneous' not in k, k
            assert 'anlık' not in k and 'anlik' not in k, k

    def test_hepsi_tasarim_noktasi_diyor(self, kunyeler):
        for k in kunyeler:
            assert ('design point' in k or 'tasarım noktası' in k), k

    def test_panonun_kendi_kunyesi_hala_dogru(self):
        """D23'te (fea-cfd a1) onarılan yarı geri gelmesin."""
        vis = oku(KOK, 'hrma', 'visualization', 'visualization.py')
        assert 'not a live reading' in vis


# =====================================================================
# P4B3-27 — hazır saha listesi TEK KAYNAK, approx bayrağı ekranda
# =====================================================================
class TestP4B327SahaListesi:

    def test_liste_urun_yolunda_okunuyor(self):
        app_py = oku(KOK, 'hrma', 'app.py')
        assert 'LAUNCH_SITE_PRESETS' in app_py
        assert 'launch_site_presets=LAUNCH_SITE_PRESETS' in app_py

    def test_sablon_kendi_kopyasini_tasimiyor(self):
        html = oku(TPL, 'launch_site.html')
        assert ('<script type="application/json" id="ls-presets-data">'
                '{{ launch_site_presets | tojson }}</script>') in html
        assert "document.getElementById('ls-presets-data')" in html
        # Eski gömülü dizinin imzası: ['id', 'Ad', enlem, boylam]
        assert not re.search(
            r"\[\s*'[a-z_]+',\s*'[^']+',\s*-?\d+\.\d+,\s*-?\d+\.\d+", html)

    def test_approx_bayragi_etikete_ulasiyor(self):
        """Metin değil DAVRANIŞ: ``presetLabel`` node'da koşturulur.

        Kaynakta ``p.approx`` geçmesi yetmez — dal ölü de olabilir.
        Fonksiyon şablondan sökülüp gerçekten çalıştırılır: yaklaşık kayıt
        etiketine ayrımı EKLEMEK ZORUNDA, tesis kaydına EKLEMEMELİ.
        """
        import json as _json
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            pytest.skip('node yok')
        html = oku(TPL, 'launch_site.html')
        js = html[html.index('function presetLabel'):]
        js = js[:js.index('\n    }') + 6]
        surucu = (
            "function t(k, fb) { return fb; }\n" + js + "\n"
            "const cikti = {"
            " yaklasik: presetLabel({name: 'Sinop (TR)', approx: true}),"
            " tesis: presetLabel({name: 'Kennedy Space Center LC-39A',"
            " approx: false}),"
            " arazi: presetLabel({name: 'Mount Everest', terrain: true,"
            " i18nKey: 'site.presetEverest'})};\n"
            "console.log(JSON.stringify(cikti));")
        r = subprocess.run([node], input=surucu, capture_output=True,
                           text=True)
        assert r.returncode == 0, r.stderr[:400]
        c = _json.loads(r.stdout.strip())
        assert c['tesis'] == 'Kennedy Space Center LC-39A', c
        assert c['yaklasik'] != 'Sinop (TR)', (
            'approx kaydı gerçek pad ile aynı biçimde görünüyor: %r' % c)
        assert 'not a launch facility' in c['yaklasik'], c
        assert 'not a launch site' in c['arazi'], c

    def test_yaklasik_kayitlar_hala_isaretli(self):
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        yaklasik = [p['id'] for p in LAUNCH_SITE_PRESETS if p['approx']]
        assert 'sinop_tr' in yaklasik and 'konya_tr' in yaklasik

    def test_arazi_referansi_saha_listesine_karismiyor(self):
        """Everest bir fırlatma sahası DEĞİL; listede aranmaz, etiketinde
        de öyle yazar."""
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        assert not any(p['id'] == 'everest' for p in LAUNCH_SITE_PRESETS)
        html = oku(TPL, 'launch_site.html')
        assert 'TERRAIN_REFS' in html and 'site.presetTerrainRef' in html

    def test_canli_olcum_kaniti_duruyor(self):
        """Canlı Chrome ölçümü (``sonra_launch_site_canli.json``): menüde
        14 Python kaydı + 1 arazi referansı; koordinatlar tek kaynakla
        birebir; iki ``approx`` kayıt etikette AYRILMIŞ, gerçek pad
        etiketi değişmemiş."""
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D24',
                           'arayuz', 'a2', 'sonra_launch_site_canli.json')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        assert d['menu_kayit_sayisi'] == d['python_kayit'] + 1
        assert d['koordinatlar_kaynakla_birebir'] is True
        assert set(d['approx_etikette_ayrildi']) == set(d['python_approx'])
        for etiket in d['approx_etikette_ayrildi'].values():
            assert 'not a launch facility' in etiket, etiket
        assert d['gercek_pad_ornegi'] == ['Kennedy Space Center LC-39A']

    def test_yeni_anahtarlar_sozlukte(self):
        s = oku(JS, 'i18n_launch_site.js')
        for a in ('site.presetEverest', 'site.presetTerrainRef',
                  'site.presetApprox'):
            assert len(sozluk_degeri(s, a)) == 2, (a, sozluk_degeri(s, a))


# =====================================================================
# OH-D21-07 — denetim patlarsa "Offline" demek kazanılmamış hükümdür
# =====================================================================
class TestOHD2107VeritabaniRozeti:

    # ÇEVRİLDİ (v3.0.1 K kulvarı, Ayberk tur 1). OH-D21-07 rozet
    # denetimi patlayınca "Offline" denmemesini ölçüyordu. ÖLÇÜLDÜ
    # (docs/scofield/raw/OH/V301/ayberk1/kaynak-cea/gorsel_once.json): denetim
    # PATLAMADAN da rozet her makinede "Offline" diyordu (CEA kolu DAİMA
    # 'local', NIST ayrıştırıcısı HİÇ eşleşmiyor) — yani "kazanılmış hüküm"
    # dalı da yanlıştı. Rozet ve yoklama söküldü. OH-D21-07'nin kazanımı
    # (bilinemeyen durum için hüküm uydurulmaz) veri kaynağı satırında
    # ölçülür: yükleme başarısızsa satır kaynak İDDİA ETMEZ.
    SAYFALAR = ('liquid.html', 'solid.html', 'advanced.html')

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_acilis_rozeti_denetlenmedi_diyor(self, sayfa):
        html = oku(TPL, sayfa)
        assert not re.search(r'class="[^"]*\b(?:database-status|cea-status|nist-status)\b', html), sayfa
        m = re.search(r'<div class="data-source-line"[^>]*>([^<]*)</div>',
                      html)
        assert m, sayfa
        assert 'Offline' not in m.group(1) and 'Connected' not in m.group(1)

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_hata_yolunda_kapali_beyani_verilmiyor(self, sayfa):
        """Kaynak yüklenemezse satır 'yüklenemedi, kaynak bildirilmiyor'
        der; kapalı/çevrimdışı hükmü vermez."""
        html = oku(TPL, sayfa)
        assert "fetch('/api/database-status')" not in html, sayfa
        if sayfa == 'advanced.html':
            i = html.index('function setOxidizerSourceFailed()')
            assert "durum: 'failed'" in html[i:i + 300]
            m = re.search(r"i18nText\('adv\.ds\.oxidizerFailed',\s*'([^']*)'",
                          html)
            assert m, 'başarısızlık metni yok'
            assert 'Offline' not in m.group(1)
            assert 'no source is stated' in m.group(1)

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_ucun_kendi_hukmu_hala_kapali_diyebiliyor(self, sayfa):
        """Aşırı kapanma ikizi: satır gerçek bir kaynağı söyleyebilmeli."""
        html = oku(TPL, sayfa)
        beklenen = {
            'advanced.html': r"adv\.ds\.oxidizerReference",
            'liquid.html': r"liq\.js\.ds_combustion_cea",
            'solid.html': r"solid\.ui\.data_source_catalogue",
        }[sayfa]
        assert re.search(beklenen, html), sayfa


# =====================================================================
# OH-D23-15 — /api/generate-3d 500'ü adıyla görünür
# =====================================================================
class TestOHD2315Uc3DHatasi:

    @pytest.fixture(scope='class')
    def adv(self):
        return oku(TPL, 'advanced.html')

    def test_iki_tuketici_de_ayni_okuyucudan_geciyor(self, adv):
        assert adv.count('read3dResponse(') == 3      # tanım + iki çağrı
        assert 'await response3d.json()' not in adv
        assert 'await response.json();\n\n                if (result.status' not in adv

    def test_yedek_tuketicinin_basarisizlik_dali_var(self, adv):
        i = adv.rindex("fetch('/api/generate-3d'")
        blok = adv[i:i + 2500]
        assert 'describe3dFailure(response3d, result3d)' in blok, (
            'yedek Plotly yolu 500 dönünce hâlâ sessizce sürüyor')

    def test_hata_metni_reason_ve_http_durumunu_tasiyor(self, adv):
        i = adv.index('function describe3dFailure')
        govde = adv[i:i + 900]
        assert 'result.reason' in govde
        assert 'response.status' in govde
        assert 'result.error' in govde

    def test_json_olmayan_govde_kendi_hatasini_gizlemiyor(self, adv):
        i = adv.index('async function read3dResponse')
        govde = adv[i:i + 500]
        assert 'non_json_response' in govde


# =====================================================================
# OH-D23-08 — yanma profili çözücüden gelir
# =====================================================================
class TestOHD2308YanmaProfili:

    @pytest.fixture(scope='class')
    def solid(self):
        return oku(TPL, 'solid.html')

    def test_durgun_uc_sinif_metni_kalmadi(self, solid):
        assert 'BATES (neutral), Star (progressive), End-burner' not in solid
        i18n = oku(JS, 'i18n_pages.js')
        assert 'solid.ui.bates_neutral_star_progressive_end_burner' not in i18n

    def test_satir_cozucunun_hukmunu_basiyor(self, solid):
        assert 'id="solid_burn_profile_line"' in solid
        assert 'function updateBurnProfileLine' in solid
        assert 'gd.burn_profile' in solid
        # Tanım VE çağrı ayrı ayrı aranır: biri sökülürse test kırmızı olur.
        assert solid.count('updateBurnProfileLine(results)') >= 2, (
            'ya tanım ya çağrı eksik')
        assert 'updateBurnProfileLine(results);\n            // c* bandı' in solid

    def test_siniflandirilamayan_kosumda_sinif_uydurulmuyor(self, solid):
        i = solid.index('function updateBurnProfileLine')
        # T-ÇAPA-C2 (27 Eki): sabit 1400 karakterlik pencere yerine işlevin
        # TAMAMI (8 boşluk girintili kapanış ayracına kadar). V301/K-C2
        # (1b3ec145b, KT-17 tanınmayan sınıf dalı) ve V301/DİL-2 (dayanak
        # cümlesi serverText kanalı) işlevi uzattı; sınıflandırılmamış dal
        # 1400. karakterin ötesine kaydı, sözleşme değişmedi.
        son = solid.index('\n        }\n', i)
        govde = solid[i:son]
        assert 'burn_profile_unclassified' in govde
        assert 'burn_profile_basis' in govde

    def test_cozucu_alani_hala_yayimliyor(self):
        motor = oku(KOK, 'hrma', 'engines', 'solid_rocket_engine.py')
        assert "'burn_profile':" in motor
        assert "'burn_profile_basis':" in motor


# =====================================================================
# OH-D23-20 — işaretli net cıvata yükü satırı
# =====================================================================
class TestOHD2320NetCivataYuku:

    @pytest.fixture(scope='class')
    def liq(self):
        return oku(TPL, 'liquid.html')

    def test_isaretli_net_yuk_satiri_var(self, liq):
        assert 'net_bolt_load_if_axial_is_compressive_N' in liq
        assert 'liq.js.gimbal_bolt_net_compressive' in liq

    def test_hukum_de_basiliyor(self, liq):
        assert 'if_axial_is_compressive_verdict' in liq
        assert 'gimbal_bolt_net_compression' in liq

    def test_alan_yoksa_sifir_uydurulmuyor(self, liq):
        """Uç ``null`` gönderdiğinde satır HİÇ basılmaz (sıfır uydurma yok)."""
        assert ("typeof d.bolts.net_bolt_load_if_axial_is_compressive_N === "
                "'number'") in liq
        i = liq.index("typeof d.bolts.net_bolt_load_if_axial_is_compressive_N")
        govde = liq[i:i + 1200]
        # Satır bu koşulun İÇİNDE kurulur
        assert govde.index('gimbal_bolt_net_compressive') > 0
        assert govde.index('gimbal_bolt_net_compressive') < 1200

    def test_uc_alani_hala_yayimliyor(self):
        gm = oku(KOK, 'hrma', 'analysis', 'gimbal_mount.py')
        assert "'net_bolt_load_if_axial_is_compressive_N':" in gm
        assert "'if_axial_is_compressive_verdict':" in gm

    def test_yeni_anahtarlar_iki_dilde(self):
        s = oku(JS, 'i18n_pages.js')
        for a in ('liq.js.gimbal_bolt_net_compressive',
                  'liq.js.gimbal_bolt_net_compression',
                  'liq.js.gimbal_bolt_net_tension'):
            assert len(sozluk_degeri(s, a)) == 2, a


# =====================================================================
# OH-D17-20 — simple/uzaytek i18n katmanı (aşama-1 gerilemesi)
# =====================================================================
# TestOHD1720SayfaI18n (2 × 2 = 4 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


# =====================================================================
# OH-D19-17 — altitude_preview başlığı eksen sırasını doğru söyler
# =====================================================================
class TestOHD1917IrtifaOnizleme:

    @pytest.fixture(scope='class')
    def adv(self):
        return oku(TPL, 'advanced.html')

    def test_cizim_gercekten_x_irtifa_y_basinc(self, adv):
        i = adv.index('function previewAltProfile')
        govde = adv[i:i + 2200]
        assert 'x: altitudes' in govde and 'y: pressures' in govde
        assert 'altitudeToPressure(alt)' in govde

    def test_baslik_eksen_sirasini_ters_soylemiyor(self, adv):
        m = re.search(r"altitudeVsPressure',\s*'([^']+)'", adv)
        assert m, 'başlık yedeği bulunamadı'
        baslik = m.group(1)
        assert not re.match(r'\s*Altitude\s+vs', baslik, re.I), baslik
        assert re.search(r'Pressure\s+vs\.?\s+Altitude', baslik, re.I), baslik

    def test_sozlukteki_iki_dil_de_duzeltildi(self):
        s = oku(JS, 'i18n_advanced.js')
        degerler = sozluk_degeri(s, 'adv.js.altitudeVsPressure')
        assert len(degerler) == 2, degerler
        for d in degerler:
            assert not re.match(r'\s*Altitude\s+vs', d, re.I), d
            assert not d.startswith('İrtifa -'), d

    def test_kunye_hala_dogru_semantigi_anlatiyor(self):
        """Kalemin başlığı KÜNYEYİ suçluyordu; künye bu ağaçta zaten
        doğruydu ve öyle kalmalı (ölçüm: once.json OH-D19-17)."""
        for dosya in ('chart_captions.js', 'i18n_shell.js'):
            for k in sozluk_degeri(oku(JS, dosya), 'chartCap.altitude_preview'):
                assert not re.search(r'vs\.?\s*time', k, re.I), (dosya, k)


# =====================================================================
# OH-D20-11 — fluxUsage izinli liste (fail-closed)
# =====================================================================
class TestOHD2011AkiHukmu:

    @pytest.fixture(scope='class')
    def prot(self):
        return oku(JS, 'panels', 'protection_panel.js')

    def test_izinli_liste_tanimli(self, prot):
        m = re.search(r"var EARNED_FLUX_KINDS\s*=\s*\[([^\]]*)\]", prot)
        assert m, 'izinli liste yok'
        turler = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        assert turler == {'computed', 'user'}, turler

    def test_yasakli_liste_geri_gelmedi(self, prot):
        assert not re.search(r"earned:\s*p\.kind\s*!==\s*'assumed'", prot)
        assert 'EARNED_FLUX_KINDS.indexOf(p.kind) !== -1' in prot

    def test_missing_turu_kazanilmis_sayilmiyor(self, prot):
        """`fluxProvenance` dört tür üretir; ikisi hüküm kazandırır."""
        turler = set(re.findall(r"kind:\s*'([a-z]+)'", prot))
        assert {'missing', 'computed', 'assumed', 'user'} <= turler, turler
        m = re.search(r"var EARNED_FLUX_KINDS\s*=\s*\[([^\]]*)\]", prot)
        izinli = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        assert 'missing' not in izinli
        assert 'assumed' not in izinli

    def test_fluxProvenance_missing_dali_duruyor(self, prot):
        assert "kind: 'missing', text: 'q_caller_W_m2 not published'" in prot


# =====================================================================
# OH-D21-11 — tavanı aşan sayfada DİLİMLİ tam sayfa kanıtı
# =====================================================================
class TestOHD2111TamSayfaKaniti:

    @pytest.fixture(scope='class')
    def tur_py(self):
        return oku(ARAC, 'browser_harness', 'tur.py')

    @pytest.fixture(scope='class')
    def den_py(self):
        return oku(ARAC, 'browser_harness', 'denetimler.py')

    def test_tur_sayfa_boyunu_olcuyor(self, tur_py):
        assert 'def _tam_sayfa_yakala' in tur_py
        assert 'scrollHeight' in tur_py
        assert "goruntuler['sayfa_boyu_px']" in tur_py

    def test_tavani_asan_sayfa_dilimleniyor(self, tur_py):
        i = tur_py.index('def _tam_sayfa_yakala')
        govde = tur_py[i:i + 5200]
        assert 'CHROMIUM_TEK_KARE_TAVANI_PX' in govde
        assert "clip={'x': 0, 'y': y0," in govde
        assert "goruntuler['tam_sayfa_dilimleri'] = dilimler" in govde
        assert "goruntuler['tam_sayfa_dilimleri'] = None" in govde  # tek kare dalı
        assert 'adim = tavan // 2' in govde
        assert 'dilimler.append(' in govde

    def test_esik_tek_kaynaktan_ithal(self, tur_py, den_py):
        """Tavan iki yerde YAZILMAZ; ikisi de esikler.py'den okur."""
        assert '16384' not in tur_py
        assert '16384' not in den_py

    def test_denetim_dilimleri_olcuyor(self, den_py):
        i = den_py.index('def tam_sayfa_goruntusu_denetimi')
        govde = den_py[i:i + 9500]
        assert "goruntuler.get('tam_sayfa_dilimleri')" in govde
        assert 'bitişik değil' in govde
        assert 'hiç görüntülenmemiş' in govde

    def test_denetim_tek_kare_yolunda_hala_kapiyi_kapatiyor(self, den_py):
        assert 'SAHTE KANIT' in den_py

    def test_canli_olcum_kaniti_duruyor(self):
        """Canlı Chrome ölçümü (``sonra_formulas_dilim.json``): /formulas
        40.604 px, tek kare tavanı aşıyor, 5 bitişik dilim sayfanın
        tamamını kaplıyor ve hiçbir iki dilim bit-aynı değil."""
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D24',
                           'arayuz', 'a2', 'sonra_formulas_dilim.json')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        assert d['sayfa_px']['yukseklik'] > d['tavan_px']
        assert d['tek_kare_tavani_asiyor'] is True
        assert d['dilim_kapsami_tam'] is True
        assert d['dilim_yukseklikleri_tavan_alti'] is True
        assert d['dilimler_ayni_mi'] is False
        assert d['dilim_kapsami_px'] == d['sayfa_px']['yukseklik']


# =====================================================================
# Sözdizimi: dokunulan her JS gerçekten ayrıştırılabiliyor mu?
# =====================================================================
def test_dokunulan_js_dosyalari_ayristirilabiliyor():
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('node yok')
    dosyalar = ['motor_viz3d.js', 'motor_viz_deck.js', 'chart_captions.js',
                'i18n_common.js', 'i18n_pages.js', 'i18n_advanced.js',
                'i18n_launch_site.js', os.path.join('panels', 'protection_panel.js')]
    for d in dosyalar:
        r = subprocess.run([node, '--check', os.path.join(JS, d)],
                           capture_output=True, text=True)
        assert r.returncode == 0, (d, r.stderr[:400])


def test_python_dosyalari_ayristirilabiliyor():
    import ast
    for yol in (os.path.join(KOK, 'hrma', 'app.py'),
                os.path.join(ARAC, 'browser_harness', 'tur.py'),
                os.path.join(ARAC, 'browser_harness', 'denetimler.py')):
        with open(yol, encoding='utf-8') as f:
            ast.parse(f.read())
    assert sys.version_info >= (3, 8)
