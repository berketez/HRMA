# -*- coding: utf-8 -*-
"""ÖH Dalga-26 / kulvar `electron` / aşama a1 — ŞART bekçileri.

İki kalem, ikisi de Fable-D20 denetçisinin ŞART'ı (defter durumu 'onarildi',
ŞART yerine getirilmemişti). Ürün davranışının kendi bekçileri
``tests/test_d20_electron_a1.py`` içindedir; BU dosya ŞART'ın LAFZINI
kilitler — yani D20 bekçisinin yeniden daraltılmasını ya da onarımın sessizce
geri alınmasını yakalar.

  P12aB4-13  `--hd-yellow` ve `--hd-blue` hiçbir CSS dosyasında tanımlı
             DEĞİLDİ; sixdof_panel.js:65/68 bu iki tanımsız değişkeni
             kullanıyordu, yani rozet renkleri tema paletinin dışında sabit
             yedeklere düşüyordu. ŞART: 65 → var(--hd-amber, #ffbe46),
             68 → var(--hd-cyan, #00e5ff); bekçinin tarama listesine
             sixdof_panel.js eklenir.
  P12aB4-15  Sunucu metni köprüsünün bekçisi ARA DEĞİŞKENLİ gösterimi
             saymıyordu (step_import_ui.js:230 `var msg = srv(...)`), bu
             yüzden oradan srv() sökülünce YEŞİL kalıyordu. ŞART: ölçüt ara
             değişkenli gösterimi de saysın (beklenen 5 nokta); olcum.py
             sayımı 4 → 5 düzeltilsin; mutasyon kaydı eklensin.

Ters mutasyon kanıtı: ``docs/scofield/raw/OH/D26/electron/a1/mutasyon.json``.
Ölçüm: aynı dizinde ``once.json`` → ``sonra.json``.
"""
import json
import os
import re

# NOT: sınıfı `from ... import` ile ÇEKMİYORUZ — pytest o sınıfın
# testlerini BU modülde ikinci kez toplar (çift koşum). Modülü içe alıp
# ölçütü öznitelik üzerinden okuyoruz: tek kaynak, tek koşum.
import tests.test_d20_electron_a1 as d20_bekci
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D20_KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D20',
                         'electron', 'a1')


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


# =========================================================================
# P12aB4-13 — tanımsız tema değişkeni (ŞART lafzı)
# =========================================================================
class TestP12aB413Sart:

    def test_sixdof_rozet_renkleri_tanimli_tokenlerden_gelir(self):
        """65/68 ŞART'ın adlandırdığı İKİ tanımlı token'ı kullanmalı."""
        s = oku('hrma/static/js/sixdof_panel.js')
        assert "yellow: 'var(--hd-amber, #ffbe46)'," in s, (
            'orta/uyarı rengi --hd-amber tokenine bağlanmamış')
        assert "blue: 'var(--hd-cyan, #00e5ff)'," in s, (
            'mavi rozet rengi --hd-cyan tokenine bağlanmamış')
        assert '--hd-yellow' not in s and '--hd-blue' not in s, (
            'CSS\'te tanımsız tema değişkeni geri geldi')

    def test_yedek_degerler_tokenin_kendi_degeriyle_ayni(self):
        """Tek kaynak: `var(--x, YEDEK)` yedeği token'ın CSS değeri olmalı.

        Aksi hâlde CSS yüklenmediğinde rozet BAŞKA bir renge düşer ve iki
        farklı 'doğru renk' ortaya çıkar (P12aB4-13'ün kökü buydu).
        """
        css = ''
        css_dizin = os.path.join(KOK, 'hrma', 'static', 'css')
        for d in sorted(os.listdir(css_dizin)):
            if d.endswith('.css'):
                css += oku('hrma/static/css/' + d)
        s = oku('hrma/static/js/sixdof_panel.js')
        ayrisan = []
        for ad, yedek in re.findall(
                r'var\((--hd-[a-z0-9-]+),\s*(#[0-9a-fA-F]{3,8})\)', s):
            tanimlar = {v.strip().lower() for v in
                        re.findall(re.escape(ad) + r'\s*:\s*([^;]+);', css)}
            if tanimlar and yedek.lower() not in tanimlar:
                ayrisan.append((ad, yedek, sorted(tanimlar)))
        assert not ayrisan, f'yedek değer token\'dan ayrışmış: {ayrisan}'

    def test_bekci_tarama_listesi_sixdof_paneli_iceriyor(self):
        """ŞART: D20 bekçisinin tarama listesine sixdof_panel.js eklenir."""
        t = oku('tests/test_d20_electron_a1.py')
        m = re.search(r'def test_bolgede_tanimsiz_hd_degiskeni_kullanilmaz'
                      r'[\s\S]*?assert not eksik', t)
        assert m, 'D20 tanımsız-değişken bekçisi bulunamadı'
        assert "'hrma/static/js/sixdof_panel.js'" in m.group(0), (
            'tarama listesi D20 kör noktasına geri döndü')


# =========================================================================
# P12aB4-15 — sunucu metni köprüsü ölçütü (ŞART lafzı)
# =========================================================================
class TestP12aB415Sart:

    #: ŞART: "beklenen 5 nokta". Ölçüm: D26/electron/a1/once.json.
    SART_NOKTALARI = {
        ('hrma/static/js/project_bar.js', 'proj.saveFailed'),
        ('hrma/static/js/project_bar.js', 'proj.loadFailed'),
        ('hrma/static/js/project_bar.js', 'proj.listFailed'),
        ('hrma/static/js/step_import_ui.js', 'var msg'),
        ('hrma/static/js/step_import_ui.js', 'message: srv(err.message)'),
    }

    def test_bes_gosterim_noktasinin_hepsi_olcute_giriyor(self):
        """Ölçüt (tek kaynak: D20 bekçisinin sınıf yöntemi) 5 noktayı görmeli."""
        noktalar = d20_bekci.TestP12aB415SunucuMetni.gosterim_noktalari()
        gorulen = set()
        for rel, _no, satir in noktalar:
            for beklenen_rel, imza in self.SART_NOKTALARI:
                if rel == beklenen_rel and imza in satir:
                    gorulen.add((beklenen_rel, imza))
        eksik = self.SART_NOKTALARI - gorulen
        assert not eksik, (
            f'ölçüt bu gösterim noktalarını görmüyor (D20 kör noktası): {eksik}')
        assert len(noktalar) >= len(self.SART_NOKTALARI)

    def test_olcum_betigi_dort_degil_bes_sayiyor(self):
        """ŞART: olcum.py sayımı 4 → 5 düzeltilir."""
        o = oku(kanit_gerekli('docs/scofield/raw/OH/D20/electron/a1/olcum.py'))
        assert 'ESKI_GOSTERIM_RE' in o and 'SUNUCU_RE' in o, (
            'D20 ölçüm betiği hâlâ yalnız eski regex ile sayıyor')
        yol = ('docs/scofield/raw/OH/D26/electron/a1/'
               'd20_olcum_duzeltilmis.json')
        d = json.loads(oku(kanit_gerekli(yol)))['P12aB4_15']
        assert d['koprulu_toplam'] == 5, (
            f"düzeltilmiş sayım 5 değil: {d['koprulu_toplam']}")
        assert d['eski_D20_regex_toplam'] == 4, (
            'eski regex sayımı 4 olarak korunmalıydı (farkın ölçüsü)')

    def test_sart_mutasyon_kaydi_D20_kanitinda(self):
        """ŞART: 'step_import_ui.js:230 srv sökülür → kırmızı' kaydı eklenir."""
        with open(kanit_gerekli(os.path.join(D20_KANIT, 'mutasyon.json')),
                  encoding='utf-8') as f:
            d = json.load(f)
        ek = d.get('D26_ek', {}).get('P12aB4-15')
        assert ek, 'D20 mutasyon kanıtına D26 ŞART kaydı eklenmemiş'
        assert ek['D26_bekcisiyle'] == 'KIRMIZI', (
            f"kayıt kırmızı demiyor: {ek['D26_bekcisiyle']}")
        assert 'srv' in ek['mutasyon'] and '230' in ek['mutasyon']
