# -*- coding: utf-8 -*-
"""ÖH D31 · arayuz-panel · aşama 3/3 — ÖK-21 FORM KATMANI BEKÇİSİ.

Kapsanan kalemler:
  * P12bB1-20 — liquid.html toplayıcısının 55 ``|| SABİT`` yedeğinden
    ucun ZORUNLU listesindeki ÜÇÜ (thrust, chamber_pressure,
    mixture_ratio) söküldü; ``/calculate_liquid``in 422
    ``incomplete_input`` kapısı ürün yolundan erişilebilir oldu.
  * OH-Z1-05 — akışkan özelliği dörtlüsü (fuel/oxidizer density +
    viscosity) hem statik ``value`` hem ``|| SABİT`` taşıyordu ve hâl
    çözümü gelmeyince bayat kalıyordu.
  * P12bS1-05 — solid.html ``two_phase_loss`` ``value="0.98"``.
  * P12bB2-03 — solid.html ``case_thickness`` ``value="8"``.
  * OH-D27-01 — app.js %20 tank marjı TAVSİYESİ hesabı engelliyordu.

Her iddia ters-mutasyonla kırmızı görüldü
(``docs/scofield/raw/OH/D31/arayuz-panel/a3/mutasyon.json``).
"""
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SABLON = os.path.join(KOK, 'hrma', 'templates')
JS = os.path.join(KOK, 'hrma', 'static', 'js')


def _oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


def _kesit(metin, bas, bit='\n        function '):
    i = metin.index(bas)
    j = metin.find(bit, i + len(bas))
    return metin[i:j if j > 0 else len(metin)]


#: Toplayıcıdaki sessiz ikame deseni (a2/a3 ölçüm betiğiyle AYNI).
IKAME = re.compile(r"getElementById\('([A-Za-z0-9_]+)'\)\.value\)?\s*\|\|\s*"
                   r"(-?\d+(?:\.\d+)?(?:e-?\d+)?)")


def _statik_value(metin, alan):
    """``<input id="alan" ... value="SAYI">`` var mı? Varsa sayıyı döndürür."""
    for kalip in (r'<input[^>]*id="%s"[^>]*?\svalue="(-?[\d.e+-]+)"',
                  r'<input[^>]*\svalue="(-?[\d.e+-]+)"[^>]*id="%s"'):
        m = re.search(kalip % alan if kalip.count('%s') == 1
                      else kalip % alan, metin)
        if m:
            return m.group(1)
    return None


# =====================================================================
# P12bB1-20 — ucun ZORUNLU listesi ile formun sessiz yedeği
# =====================================================================
class TestP12bB120ZorunluAlanlar:
    """Ucun 422 kapısı ürün yolundan KOŞABİLMELİ."""

    #: Ucun kendi listesi burada TEKRAR YAZILMAZ — app.py'den okunur.
    @staticmethod
    def _uc_kritik_girdileri():
        kaynak = _oku('hrma', 'app.py')
        m = re.search(r"KRITIK_GIRDILER = \(([^)]*)\)", kaynak, re.S)
        assert m, 'app.py KRITIK_GIRDILER tanımı bulunamadı'
        return [a.strip().strip("'\"")
                for a in m.group(1).split(',') if a.strip()]

    def test_uc_listesi_okunabiliyor(self):
        adlar = self._uc_kritik_girdileri()
        assert 'thrust' in adlar and 'chamber_pressure' in adlar
        assert 'mixture_ratio' in adlar

    def test_zorunlu_alanlarda_sessiz_yedek_yok(self):
        """Zorunlu alan boş bırakılınca gövdeye SAYI gitmemeli."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        toplayici = _kesit(liq, 'function collectAllParameters() {')
        ikame = {m.group(1): m.group(2) for m in IKAME.finditer(toplayici)}
        kirli = {a: ikame[a] for a in self._uc_kritik_girdileri()
                 if a in ikame}
        assert kirli == {}, (
            'liquid.html toplayıcısı ucun ZORUNLU alanlarında hâlâ sessiz '
            'sabit gönderiyor; 422 incomplete_input kapısı ürün yolundan '
            'erişilemez kalır: %r' % kirli)

    def test_zorunlu_alanlarda_statik_value_yok(self):
        """Form, kullanıcı adına tasarım noktası SEÇMEZ."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        kirli = {a: _statik_value(liq, a)
                 for a in self._uc_kritik_girdileri()
                 if _statik_value(liq, a) is not None}
        assert kirli == {}, (
            'liquid.html zorunlu alanları hâlâ statik value taşıyor: %r'
            % kirli)

    def test_zorunlu_alanlar_placeholder_ile_yonlendiriyor(self):
        """Söküm kullanıcıyı sessiz bırakmaz: ekranda ne yapacağı yazar."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        for alan in ('thrust', 'chamber_pressure', 'mixture_ratio'):
            assert re.search(r'<input[^>]*id="%s"[^>]*placeholder=' % alan,
                             liq), alan

    def test_resetForm_zorunlu_alani_doldurmuyor(self):
        liq = _oku('hrma', 'templates', 'liquid.html')
        reset = _kesit(liq, 'function resetForm() {')
        for alan in ('thrust', 'chamber_pressure', 'mixture_ratio'):
            m = re.search(r"getElementById\('%s'\)\.value = '([^']*)';"
                          % alan, reset)
            assert m is None or m.group(1) == '', (alan, m and m.group(1))

    def test_optional_yardimcisi_bos_alanda_undefined_veriyor(self):
        """``liqOptNum`` boş/çözülemeyen alanda anahtar ÜRETMEZ."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        govde = _kesit(liq, 'function liqOptNum(id) {')
        assert "if (ham === '') { return undefined; }" in govde
        assert 'Number.isFinite(v) ? v : undefined' in govde
        # null gönderimi de yasak: yardımcı hiçbir dalda null dönmüyor
        assert 'return null' not in govde


# =====================================================================
# OH-Z1-05 — akışkan özelliği dörtlüsü + bayat sayı
# =====================================================================
Z1_ALANLAR = ('fuel_density', 'oxidizer_density',
              'fuel_viscosity', 'oxidizer_viscosity')


class TestOHZ105AkiskanOzellikleri:

    def test_toplayicida_sessiz_yedek_yok(self):
        liq = _oku('hrma', 'templates', 'liquid.html')
        toplayici = _kesit(liq, 'function collectAllParameters() {')
        ikame = {m.group(1): m.group(2) for m in IKAME.finditer(toplayici)}
        kirli = {a: ikame[a] for a in Z1_ALANLAR if a in ikame}
        assert kirli == {}, (
            'akışkan özelliği alanı boşken gövdeye sabit gidiyor '
            '(LH2 seçiliyken RP-1 in 810 kg/m3 ü): %r' % kirli)

    def test_statik_value_yok_placeholder_var(self):
        liq = _oku('hrma', 'templates', 'liquid.html')
        for alan in Z1_ALANLAR:
            assert _statik_value(liq, alan) is None, alan
            assert re.search(r'<input[^>]*id="%s"[^>]*placeholder=' % alan,
                             liq), alan

    def test_resetForm_sabit_yazmiyor(self):
        liq = _oku('hrma', 'templates', 'liquid.html')
        reset = _kesit(liq, 'function resetForm() {')
        for alan in Z1_ALANLAR:
            m = re.search(r"getElementById\('%s'\)\.value = '([^']*)';"
                          % alan, reset)
            assert m is None or m.group(1) == '', (alan, m and m.group(1))

    def test_cozulmeyen_halde_alan_temizleniyor(self):
        """Hâl çözümü yoksa bir ÖNCEKİ akışkanın sayısı ekranda kalmaz."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        assert 'function liquidClearUnresolvedField(' in liq
        # dört alanın dördü için de else dalı var
        for alan in Z1_ALANLAR:
            assert "liquidClearUnresolvedField('%s');" % alan in liq, alan
            assert "liquidAutofillField('%s'," % alan in liq, alan

    def test_elle_yazilan_deger_temizlenmiyor(self):
        """Temizleme YALNIZ makinenin doldurduğu alana dokunur.

        KÖR NOKTA (ters-mutasyonla ölçüldü): gövde ``_kesit`` ile
        kesilince dilim bir SONRAKİ ``function`` anahtarına kadar
        uzuyor ve aradaki genel ``input`` dinleyicisini de içine
        alıyordu; koruma sökülse bile dinleyicinin kendi bayrak
        sınaması testi YEŞİL tutuyordu. Dilim artık işlevin kendi
        kapanış parantezinde bitiyor.
        """
        liq = _oku('hrma', 'templates', 'liquid.html')
        bas = liq.index('function liquidClearUnresolvedField(fieldId) {')
        govde = liq[bas:liq.index('\n        }\n', bas)]
        assert 'if (liquidAutofillMi(el))' in govde, (
            'temizleme koruması söküldü: elle yazılan sayı da siliniyor')
        assert "el.value = '';" in govde
        assert 'liquidAutofillBayragi(el, false);' in govde
        # kullanıcı alana dokununca bayrak kalkar (ayrı dinleyici)
        dinleyici = _kesit(liq, "document.addEventListener('input',",
                           '\n        }, true);')
        assert 'liquidAutofillMi(el)' in dinleyici
        assert 'liquidAutofillBayragi(el, false);' in dinleyici
        # bayrak okuma/yazma DOM sapmasına dayanıklı: değer ÖNCE yazılır
        yaz = _kesit(liq, 'function liquidAutofillField(fieldId, deger) {')
        assert yaz.index('el.value = deger;') < yaz.index(
            'liquidAutofillBayragi(el, true);'), (
            'bayrak değerden ÖNCE konuyor: dataset olmayan bir DOM da '
            'değeri hiç yazmaz (z5guard d3 dersi)')

    def test_ezme_kapisi_duruyor(self):
        """P12bB1-02 kapısı SÖKÜLMEDİ: kategori yedeği alanı EZMEZ."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        assert 'function propellantProvenance(' in liq
        assert liq.count('prov.stateResolved && props.density') == 2
        assert liq.count('prov.stateResolved && props.viscosity') == 2


# =====================================================================
# P12bS1-05 + P12bB2-03 — solid.html iki alan
# =====================================================================
class TestSolidFormKatmani:

    @pytest.mark.parametrize('alan', ['two_phase_loss', 'case_thickness'])
    def test_statik_value_yok(self, alan):
        sol = _oku('hrma', 'templates', 'solid.html')
        assert _statik_value(sol, alan) is None, (
            '%s hâlâ form sabiti taşıyor; kullanıcı seçmediği bir çarpanı '
            'sonuçta görüyor' % alan)

    @pytest.mark.parametrize('alan', ['two_phase_loss', 'case_thickness'])
    def test_toplayicida_sessiz_yedek_yok(self, alan):
        sol = _oku('hrma', 'templates', 'solid.html')
        toplayici = _kesit(sol, 'function collectAllParameters() {')
        ikame = {m.group(1): m.group(2) for m in IKAME.finditer(toplayici)}
        assert alan not in ikame, (alan, ikame.get(alan))
        assert "%s: solOptNum('%s')," % (alan, alan) in toplayici

    @pytest.mark.parametrize('alan', ['two_phase_loss', 'case_thickness'])
    def test_placeholder_cozucu_sozlesmesini_soyluyor(self, alan):
        sol = _oku('hrma', 'templates', 'solid.html')
        assert re.search(r'<input[^>]*id="%s"[^>]*placeholder=' % alan,
                         sol), alan

    def test_cozucu_varsayilani_beyanli(self):
        """Söküm KARŞI AYAĞI: çözücü kendi hükmünü ADIYLA yayımlıyor."""
        motor = _oku('hrma', 'engines', 'solid_rocket_engine.py')
        assert "'two_phase_efficiency_applied'" in motor
        assert "'two_phase_losses_applied'" in motor
        assert 'def _case_thickness_is_user_supplied' in motor

    def test_tanilama_blogu_ekrana_basiliyor(self):
        """19 alanlık iki-faz teşhis bloğu şablonda basılıyor."""
        sol = _oku('hrma', 'templates', 'solid.html')
        assert sol.count('twoPhaseDiagnosticHTML(') >= 2


# =====================================================================
# OH-D27-01 — tavsiye hesabı engellemez
# =====================================================================
class TestOHD2701TankMarjiTavsiyesi:

    def test_marj_tavsiyesi_errors_dizisinde_degil(self):
        js = _oku('hrma', 'static', 'js', 'app.js')
        blok = _kesit(js, '// Detailed tank pressure validation',
                      '// Additional range checks')
        marj = blok[blok.index('chamber_pressure * 1.2) {'):]
        assert "errors.push(TF('app.val.tankMargin'" not in marj, (
            '%20 marj TAVSİYESİ hâlâ engelleyici hata dizisinde; sağlıklı '
            'tasarım "Input validation failed" ile reddediliyor')
        assert "advisories.push(TF('app.val.tankMargin'" in marj

    def test_tavsiye_kanali_var_ve_susturulmuyor(self):
        js = _oku('hrma', 'static', 'js', 'app.js')
        govde = _kesit(js, 'function validateInputs(data) {',
                       '\n// Display results')
        assert 'const advisories = [];' in govde
        assert 'showWarning(advisories.join(' in govde

    def test_sert_hukum_duruyor(self):
        """Tank <= hazne hâlâ ENGELLEYİCİ (ÖK-22: kapsam daralmaz)."""
        js = _oku('hrma', 'static', 'js', 'app.js')
        blok = _kesit(js, '// Detailed tank pressure validation',
                      '// Additional range checks')
        assert "errors.push(T('app.val.tankPositive'" in blok
        assert "errors.push(TF('app.val.tankTooLow'" in blok


# =====================================================================
# Çevrim kapısı ölçümü — kalemin İDDİASI (OH-D27-01 başlığı) çürütüldü
# =====================================================================
class TestCevrimKapisiOlcumu:
    """app.js çevrim kapılı uca KONUŞMUYOR; kalem başlığı bu yüzden düştü.

    Bekçi, ölçümün gelecekte sessizce değişmesini engeller: app.js
    çevrim kapılı uca konuşmaya başlarsa bu test kırmızı verir ve
    kalem yeniden açılır.
    """

    def test_app_js_yalniz_hibrit_ucuna_konusuyor(self):
        js = _oku('hrma', 'static', 'js', 'app.js')
        uclar = set(re.findall(r"fetch\('(/[a-z_0-9-]+)'", js))
        assert '/calculate_liquid' not in uclar, (
            'app.js artık çevrim kapılı uca konuşuyor; tank kuralı '
            'sunucu sözleşmesiyle ÇELİŞİR — OH-D27-01 yeniden açılmalı')
        assert '/calculate' in uclar

    def test_app_js_yalniz_advanced_html_tarafindan_yukleniyor(self):
        yukleyen = sorted(
            f for f in os.listdir(SABLON) if f.endswith('.html')
            and 'js/app.js' in open(os.path.join(SABLON, f),
                                    encoding='utf-8').read())
        assert yukleyen == ['advanced.html'], yukleyen

    def test_advanced_html_hibrit_gonderiyor(self):
        adv = _oku('hrma', 'templates', 'advanced.html')
        assert set(re.findall(r"motor_type:\s*'([a-z]+)'", adv)) == {'hybrid'}

    def test_liquid_html_tank_pressure_alani_tasimiyor(self):
        """Çevrim kapılı ucun sayfası zaten ``feed_pressure`` kullanıyor."""
        liq = _oku('hrma', 'templates', 'liquid.html')
        assert 'id="tank_pressure"' not in liq
        assert 'id="feed_pressure"' in liq

    def test_cevrim_kapisi_calculate_liquid_icinde(self):
        app_py = _oku('hrma', 'app.py')
        i = app_py.index("@app.route('/calculate_liquid'")
        assert 'tank_pressure_not_read_in_turbopump_cycle' in app_py[i:]


# =====================================================================
# ÖK-21 KÜME GERİLEME KİLİDİ (P12bS1-01 ölçüsü)
# =====================================================================
class TestOK21KumeGerilemesi:
    """Sökülen alanlar geri gelmesin; yenisi çift katmanla doğmasın."""

    SINIR = {
        # a3 sonrası ölçüm (docs/.../a3/sonra.json M7); yalnız AZALABİLİR
        'liquid.html': {'value': 54, 'ikame': 48},
        'solid.html': {'value': 70, 'ikame': 63},
        'advanced.html': {'value': 72, 'ikame': 25},
    }

    @pytest.mark.parametrize('dosya', sorted(SINIR))
    def test_kume_buyumuyor(self, dosya):
        metin = _oku('hrma', 'templates', dosya)
        deger = len(set(
            re.findall(r'<input[^>]*id="([A-Za-z0-9_]+)"[^>]*'
                       r'value="-?\d+(?:\.\d+)?(?:e-?\d+)?"', metin)))
        ikame = len(set(m.group(1) for m in IKAME.finditer(metin)))
        assert deger <= self.SINIR[dosya]['value'], (
            '%s sayısal value alanı ARTTI (%d > %d): yeni bir form sabiti '
            'eklenmiş' % (dosya, deger, self.SINIR[dosya]['value']))
        assert ikame <= self.SINIR[dosya]['ikame'], (
            '%s sessiz ikame ARTTI (%d > %d)'
            % (dosya, ikame, self.SINIR[dosya]['ikame']))


# =====================================================================
# Ölçüm dosyaları — rapor iddiaları kanıt dosyasına bağlı
# =====================================================================
class TestKanitDosyalari:

    KANIT = os.path.join('docs', 'scofield', 'raw', 'OH', 'D31',
                         'arayuz-panel', 'a3')

    @pytest.mark.parametrize('ad', ['once.json', 'sonra.json',
                                    'once_canli.json'])
    def test_olcum_dosyasi_var(self, ad):
        yol = os.path.join(KOK, self.KANIT, ad)
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            json.load(f)

    def test_canli_olcum_uc_kapisini_gosteriyor(self):
        with open(kanit_gerekli(os.path.join(KOK, self.KANIT, 'once_canli.json')),
                  encoding='utf-8') as f:
            d = json.load(f)
        a = d['A_kritik_kapi']
        assert a['uc_alan_dusunce_kod'] == 422
        assert a['missing_fields'] == ['thrust', 'chamber_pressure',
                                       'mixture_ratio']
        b = d['B_yogunluk_bayatligi']
        # form yedeği LH2 gövdesine RP-1 in yoğunluğunu sokuyordu
        assert b['form_yedegi_rho_fuel'] == 810.0
        assert b['alan_yok_rho_fuel'] == 70.85
        assert b['form_yedegi_kaynak'] == 'user input'
        c = d['C_two_phase_loss']
        assert c['form_sabiti_eta_uygulanan'] == 0.98
        assert c['alan_yok_eta_uygulanan'] == 1.0
        assert c['hesaplanan_uygulandi'] is False
