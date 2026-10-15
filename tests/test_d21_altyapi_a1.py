# -*- coding: utf-8 -*-
"""ÖH Dalga-21 · kulvar `altyapi` · aşama 1 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve o kalemin kusurunu TERS
MUTASYONLA gördüğü doğrulanmıştır (kanıt:
``docs/scofield/raw/OH/D21/altyapi/a1/mutasyon.json``).
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[1]
ISAKISI = DEPO / '.github' / 'workflows'


# ---------------------------------------------------------------------------
# P17B1-14 — CFD kiracısının KAPSAM BEYANI denetime bağlı mı?
# ---------------------------------------------------------------------------
class TestP17B114ViskozsuzBeyani:
    """Fixture 9 rozette kilitliyken ürün 10 basıyordu; eksik olan rozet
    modelin kapsam sınırıydı (INVISCID / Euler — duvar kayması yok).

    Canlı ölçüm 4 Eylül 2026, sistem Chrome 152.0.7977.82, üç sayfanın
    üçünde de ekrandaydı ('dim' renginde):
    ``docs/scofield/raw/OH/D21/altyapi/a1/tur_kiyas.json``.
    """

    def test_imza_esiklerde_TANIMLI_ve_iki_dilli(self):
        from tools.browser_harness import esikler
        imza = esikler.ROZET_IMZALARI['cfd_viskozsuz_beyani']
        assert 'INVISCID' in imza['varyantlar']
        # Türkçe varyant ZORUNLU: tur en-US koşsa da arayüz çevrilebilir ve
        # imza dile bağlı kalırsa TR oturumda kör olur.
        assert any('VİSKOZSUZ' in v for v in imza['varyantlar'])
        assert imza['sozluk_anahtarlari'] == ('panel.cfd.badgeInviscid',)

    def test_sozluk_anahtari_urunde_GERCEKTEN_var(self):
        """İmza ürünün anahtarına bağlıdır; anahtar kaybolursa bekçi uyarır."""
        js = (DEPO / 'hrma/static/js/panels/cfd_panel.js').read_text(
            encoding='utf-8')
        assert "panel.cfd.badgeInviscid" in js
        sozluk = (DEPO / 'hrma/static/js/i18n_common.js').read_text(
            encoding='utf-8')
        # EN + TR: iki karşılık da sözlükte olmalı.
        assert sozluk.count("'panel.cfd.badgeInviscid'") >= 2

    def test_imza_KOSULLU_cift_olarak_denetleniyor(self):
        """ÖH D26 / P17B1-14 (Fable ŞARTI) — ÇEVRİLDİ.

        Bu iddia D21'de ``'cfd_viskozsuz_beyani' in
        CFD_KIRACISI.beklenen_imzalar`` diyordu ve o hâliyle KUSURU
        KORUYORDU: imzayı KOŞULSUZ beklenen listesinde tutmayı şart
        koşuyordu, oysa ürün onu yalnız viskozsuz koşumda basar
        (cfd_panel.js::viscousBadgesHtml — ``if (!v.enabled)``).

        Ölçüldü (taban 7751531,
        docs/scofield/raw/OH/D26/altyapi/a1/once_viskoz.json):
          * viskoz koşumda ekranda INVISCID varken denetim YEŞİL
            (yalancı yeşil — ürünün en ağır beyanı tersine dönmüş olurdu),
          * viskoz koşumda doğru rozet (VISCOUS —) varken KIRMIZI
            (yalancı kırmızı — harness viskoz yapılandırmada koşamazdı).

        D21'in kazanımı KORUNUR: imza hâlâ denetleniyor, artık koşulsuz
        listede değil koşullu çift olarak — yükün ``viscous_enabled``
        alanına göre biri BEKLENEN öteki YASAK.
        """
        from tools.browser_harness import esikler, sayfalar
        K = sayfalar.CFD_KIRACISI
        assert 'cfd_viskozsuz_beyani' not in K.beklenen_imzalar, (
            'imza koşulsuz beklenen listesine geri konmuş — viskoz koşumda '
            'yalancı kırmızı verir')
        assert 'cfd_viskoz_kipi' in esikler.ROZET_IMZALARI, (
            'çiftin viskoz ayağı imza tablosundan düşmüş; tek ayak kalırsa '
            'öteki dal denetimsiz kalır')
        # Koşulun ürün yükünden okunduğunun kanıtı.
        assert any(a[0] == 'viscous_enabled' and a[1] == 'viscous.enabled'
                   for a in K.yuk_alanlari), (
            'viscous_enabled yük listesinden düşmüş — koşul okunamaz, '
            'denetim hüküm veremez')

    def test_rozet_kaybolunca_denetim_KIRMIZI(self):
        """Kalemin ta kendisi: beyan ekrandan düşerse tur bunu görmeli."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        from tools.browser_harness import denetimler, sayfalar
        tam = cfd_olcumu()
        assert tam['rozet_sayisi'] == 10, tam['rozet_sayisi']
        d = denetimler.merkez_rozet_denetimi(
            'cfd', tam, sayfalar.CFD_KIRACISI.beklenen_imzalar,
            sayfalar.CFD_KIRACISI.yasak_imzalar,
            sayfalar.CFD_KIRACISI.notr_imzalar)
        assert d.gecti, d.ozet

        eksik = dict(tam)
        eksik['rozetler'] = [r for r in tam['rozetler']
                             if 'INVISCID' not in r['metin']]
        eksik['rozet_sayisi'] = len(eksik['rozetler'])
        eksik['metin'] = ' '.join(r['metin'] for r in eksik['rozetler'])
        d2 = denetimler.merkez_rozet_denetimi(
            'cfd', eksik, sayfalar.CFD_KIRACISI.beklenen_imzalar,
            sayfalar.CFD_KIRACISI.yasak_imzalar,
            sayfalar.CFD_KIRACISI.notr_imzalar)
        assert not d2.gecti, (
            'kapsam beyanı ekrandan düştüğü hâlde denetim YEŞİL kaldı — '
            'kullanıcı Euler koşusunu viskoz sanabilir ve kimse uyarmaz')
        assert 'cfd_viskozsuz_beyani' in d2.ozet


# ---------------------------------------------------------------------------
# P17B1-16 — görsel kapı ürünün KAÇ sayfasını açıyor?
# ---------------------------------------------------------------------------
class TestP17B116GorselKapiKapsami:
    """Tur 3 sayfa geziyordu, ürünün (muaf iki artık hariç) 6 sayfası var.

    Canlı ölçüm (4 Eylül 2026): 3 → 6 sayfa, 52 → 70 denetim; yeni açılan
    üç sayfadan ikisi TEMİZ, biri (``/formulas``) gerçek bir kusur verdi
    (tam sayfa görüntüsü 40 604 px — Chromium tek kare tavanının üstünde,
    yani kanıtın kendisi sahte).
    """

    def test_uc_statik_sayfa_TANIMLI(self):
        from tools.browser_harness import sayfalar
        assert set(sayfalar.STATIK_SAYFALAR) == {'index', 'formulas',
                                                 'launch-site'}
        for tanim in sayfalar.STATIK_SAYFALAR.values():
            assert tanim.hesap_var is False
            assert tanim.hesapla_secici == ''
            assert tanim.merkez_var is False
            assert tanim.fea_panelleri == ()

    def test_varsayilan_sira_ALTI_sayfa(self):
        from tools.browser_harness import sayfalar
        assert len(sayfalar.VARSAYILAN_SIRA) == 6
        assert set(sayfalar.VARSAYILAN_SIRA) == set(sayfalar.SAYFALAR)

    def test_yollar_uygulamada_var(self):
        from hrma.app import app
        from tools.browser_harness import sayfalar
        kurallar = {str(k.rule) for k in app.url_map.iter_rules()}
        for tanim in sayfalar.STATIK_SAYFALAR.values():
            assert tanim.yol in kurallar, tanim.yol

    def test_hesapsiz_sayfada_HAYALET_denetim_uretilmez(self):
        """3B tuvali olmayan sayfayı 'tuval boş' diye suçlamak kusurdur.

        Kaynak AST'si okunur: ``tuval_denetimi``/``plume_denetimi`` ve
        Merkez denetimleri ``hesap_var`` kapısının İÇİNDE olmalı.
        """
        from tools.browser_harness import tur
        kaynak = inspect.getsource(tur.SayfaGezgini._rapor)
        agac = ast.parse(kaynak.lstrip())
        kapili = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.If):
                kosul = ast.unparse(dugum.test)
                if 'hesap_var' not in kosul:
                    continue
                for alt in ast.walk(dugum):
                    if isinstance(alt, ast.Attribute):
                        kapili.add(alt.attr)
        for ad in ('tuval_denetimi', 'plume_denetimi', 'merkez_denetimleri'):
            assert ad in kapili, (
                f'{ad} hesap_var kapısının dışında — hesapsız sayfada '
                'hayalet denetim üretilir ve kapı okunamaz hâle gelir')

    def test_hesapsiz_dal_akisi_KESMEZ(self):
        """Hesapsız sayfa kendi istisnasıyla biter; `hatalar`a yazmaz."""
        from tools.browser_harness import tur
        kaynak = inspect.getsource(tur.SayfaGezgini.gez)
        assert '_HesapsizSayfaBitti' in kaynak
        # İstisna, ANA try'ın genel `except Exception` dalından ÖNCE
        # yakalanmalı; sonra yakalanırsa "AKIŞ KESİLDİ" yazılır ve sayfa
        # haksız yere kırmızı olur. Sıra AST'den okunur: gövdede başka
        # (iç içe) try blokları da var, dizge araması onları karıştırır.
        islev = ast.parse(kaynak.lstrip()).body[0]
        ana_try = next(d for d in islev.body if isinstance(d, ast.Try)
                       and d.finalbody)
        adlar = [ast.unparse(h.type) if h.type else '*'
                 for h in ana_try.handlers]
        assert adlar[:2] == ['_HesapsizSayfaBitti', 'Exception'], adlar
        ozel = ana_try.handlers[0]
        # Bu dal `self.hatalar`a HİÇBİR ŞEY yazmamalı.
        assert 'self.hatalar' not in ast.unparse(ozel)

    def test_urunun_her_sayfasi_kapali_MANDAL(self):
        """P17B1-16 mandalı `tests/test_browser_harness.py`de yaşıyor —
        burada varlığı kilitlenir ki sessizce silinmesin."""
        metin = (DEPO / 'tests/test_browser_harness.py').read_text(
            encoding='utf-8')
        assert 'test_urunun_HER_html_sayfasi_ya_turda_ya_gerekceli_muaf' in metin


# ---------------------------------------------------------------------------
# OH-D17-19 — atlama bütçesi TEK KAYNAK
# ---------------------------------------------------------------------------
class TestOHD1719AtlamaButcesiTekKaynak:
    """Bütçe 76 iki yerde yazılıydı: modül + `tests.yml` gövdesi."""

    ADLAR = ('ATLAMA_BUTCESI', 'TOPLANAN_TABANI', 'DEPO_KOKLERI')

    def test_uc_esik_de_TEK_yerde_tanimli(self):
        modul = (DEPO / 'tools/atlama_kapisi.py').read_text(encoding='utf-8')
        yml = (ISAKISI / 'tests.yml').read_text(encoding='utf-8')
        for ad in self.ADLAR:
            modulde = re.findall(r'^%s\s*=' % ad, modul, re.M)
            assert len(modulde) == 1, (ad, modulde)
        for ad in ('BUTCE', 'TOPLANAN_TABANI', 'DEPO_KOKLERI'):
            kopya = re.findall(r'^\s*%s\s*=\s*([\'"(\d][^\n]*)$' % ad, yml, re.M)
            assert not kopya, (
                f'tests.yml içinde {ad} SABİT olarak yeniden yazılmış: {kopya}')

    def test_yml_govdesi_kaynagi_AST_ile_okuyor(self):
        yml = (ISAKISI / 'tests.yml').read_text(encoding='utf-8')
        assert "pathlib.Path('tools/atlama_kapisi.py')" in yml
        assert "_esik('ATLAMA_BUTCESI')" in yml
        assert "_esik('TOPLANAN_TABANI')" in yml
        assert "_esik('DEPO_KOKLERI')" in yml
        # İTHAL DEĞİL: gövde exec edildiğinde `tools` paketi ithal edilebilir
        # olmayabilir; ithal biçimi sessizce çökerdi.
        assert 'from tools.atlama_kapisi import' not in yml

    def test_kaynak_okunamazsa_adim_DUSER(self):
        """FAIL-CLOSED: eşik ölçülemiyorsa geçer not verilemez."""
        yml = (ISAKISI / 'tests.yml').read_text(encoding='utf-8')
        i = yml.index("_KAYNAK = pathlib.Path('tools/atlama_kapisi.py')")
        pencere = yml[i:i + 1600]
        assert 'sys.exit' in pencere
        assert 'if not _KAYNAK.is_file()' in pencere

    def test_davranis_bekcisi_gercek_butceyi_kullaniyor(self):
        """`test_faz4_yayin_kapisi` artık sayıyı gövdeden değil kaynaktan alır."""
        metin = (DEPO / 'tests/test_faz4_yayin_kapisi.py').read_text(
            encoding='utf-8')
        assert 'from tools.atlama_kapisi import ATLAMA_BUTCESI' in metin
        assert '_tek_kaynagi_kur' in metin


# ---------------------------------------------------------------------------
# OH-D19-05 — kapının `data/` tabanı git indeksinden mi?  (ÇÜRÜTME kilidi)
# ---------------------------------------------------------------------------
class TestOHD1905RepoDataTabani:
    """Kalem başlığı ("çalışma ağacındaki gitignore'lu dosyaları sayıyor")
    bu ağaçta ÖLÇÜMLE ÇÜRÜTÜLDÜ: onarım D19'da (21ecbe9) yapılmış.

    Bekçi yeni bir onarımı değil, çürütmenin dayanağını kilitler: taban
    çalışma ağacına GERİ DÖNERSE kırmızı yanar.
    """

    def test_taban_git_ls_files_ile_aliniyor(self):
        metin = (DEPO / 'packaging/release_gate.sh').read_text(encoding='utf-8')
        kod = '\n'.join(s for s in metin.splitlines()
                        if not s.lstrip().startswith('#'))
        assert re.search(r'REPO_DATA="\$\(git -C "\$SRC" ls-files data', kod), (
            'REPO_DATA tabanı git indeksinden alınmıyor — makineden makineye '
            'değişen bir sayı kapıyı yanlış kırmızıya çevirir')
        assert not re.search(r'find\s+"\$SRC/data"', kod), (
            'kapı `data/` tabanını yine çalışma ağacından sayıyor; '
            'gitignore\'lu propellant_cache/ ve experimental_data.db tabanı '
            'şişirir')

    def test_taban_okunamazsa_FAIL_CLOSED(self):
        metin = (DEPO / 'packaging/release_gate.sh').read_text(encoding='utf-8')
        i = metin.index('REPO_DATA="$(git -C "$SRC" ls-files data')
        assert 'basarisiz' in metin[i:i + 500]


if __name__ == '__main__':          # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))
