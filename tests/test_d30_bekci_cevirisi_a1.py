"""ÖH Dalga-30 · kulvar **bekci-cevirisi**, aşama 1 — onarımın bekçisi.

Tek kalem: **OH-D29-12** — "iddiasız test nüfusu tavanı 51'e YAPIŞIK".

fix-28a ölçümü kusuru adıyla koymuştu: ``IDDIASIZ_DELEGESIZ_TAVANI``
elle yazılmış 51'di, ölçüm de 51 veriyordu, pay SIFIRDI. Kapı yalnız SAYI
sayıyordu ve iki deliği vardı (ikisi de ÖLÇÜLDÜ, kanıt
``docs/scofield/raw/OH/D30/bekci-cevirisi/a1/mutasyon.json``):

* **takas körlüğü** — bir delegesiz test çıkıp yerine başkası girdiğinde
  sayı 51'de kalıyor ve kapı YEŞİL geçiyordu (mutasyon B);
* **sahte pay** — bir kalem iddia kazanınca sayı 50'ye düşüyor, tavan 51
  kalıyor ve denetlenmemiş yeni bir teste sessizce yer açıyordu
  (mutasyon A).

Onarım: 51 kalemin TAMAMI ``DELEGESIZ_ENVANTERI`` içinde nitelikli adı
(``dosya::Sınıf::ad``) ve ÖLÇÜLMÜŞ gerekçesiyle hükme bağlandı; tavan
envanterden TÜRETİLDİ; dört kapı eklendi (yeni giriş, bayat satır, mutlak
tavan, gerekçe–kredi kaynağı ilişkisi).

Bu dosya ÜRÜNÜ değil ONARIMIN GERİ ALINAMAZLIĞINI kilitler: aşağıdaki
iddialar, kapının bir gün yeniden "elle yazılmış sayı"ya dönmesini ve
niteliksiz anahtara geri düşmesini engeller.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:                             # pragma: no cover
    sys.path.insert(0, str(KOK))

d22 = importlib.import_module('tests.test_d22_bekci_cevirisi_a1')

#: D25'te ÖLÇÜLEN sayı. ÖK-22: yalnız DÜŞER, yükselmez.
D25_OLCUMU = 51


def _d22_agaci():
    yol = KOK / 'tests' / 'test_d22_bekci_cevirisi_a1.py'
    return ast.parse(yol.read_text(encoding='utf-8'))


def _atama_degeri(agac, ad):
    """Modül düzeyindeki ``ad = ...`` atamasının SAĞ TARAF düğümü."""
    for d in agac.body:
        if isinstance(d, ast.Assign):
            for h in d.targets:
                if isinstance(h, ast.Name) and h.id == ad:
                    return d.value
        if isinstance(d, ast.AnnAssign) and isinstance(d.target, ast.Name) \
                and d.target.id == ad:
            return d.value
    return None


class TestOHD2912KumeOlcusu:
    """Sayı kapısı KÜME kapısına çevrildi ve geri dönemez."""

    def test_tavan_elle_yazilmis_sayi_degil_envanterden_turetiliyor(self):
        """Geri dönüşün ADI budur: ``IDDIASIZ_DELEGESIZ_TAVANI = 52``.

        Kusur sayının 51 olması değil, tavanın ELLE yazılabilir olmasıydı:
        kapı kırmızı verdiğinde sayıyı bir artırmak en kolay yoldu (ÖK-22
        gevşetmesi). Tavan artık envanterin BOYU olmak zorunda — yeni bir
        kaleme yer açmak, o kalemi adıyla ve gerekçesiyle yazmayı gerekli
        kılar.
        """
        deger = _atama_degeri(_d22_agaci(), 'IDDIASIZ_DELEGESIZ_TAVANI')
        assert deger is not None, 'IDDIASIZ_DELEGESIZ_TAVANI atanmıyor'
        assert not isinstance(deger, ast.Constant), (
            'delegesiz tavanı yeniden elle yazılmış sabite döndürülmüş '
            '(%r); envanterden türetilmeli' % getattr(deger, 'value', None))
        assert (isinstance(deger, ast.Call)
                and getattr(deger.func, 'id', '') == 'len'
                and getattr(deger.args[0], 'id', '')
                == 'DELEGESIZ_ENVANTERI'), (
            'tavan len(DELEGESIZ_ENVANTERI) değil: %s' % ast.dump(deger)[:120])
        assert d22.IDDIASIZ_DELEGESIZ_TAVANI == len(d22.DELEGESIZ_ENVANTERI)

    def test_mutlak_tavan_yukselmedi(self):
        """ÖK-22 — D25 ölçümü bir üst sınırdır, yalnız düşürülebilir."""
        assert d22.DELEGESIZ_MUTLAK_TAVAN <= D25_OLCUMU, (
            'mutlak tavan yükseltilmiş: %d > %d'
            % (d22.DELEGESIZ_MUTLAK_TAVAN, D25_OLCUMU))
        assert len(d22.DELEGESIZ_ENVANTERI) <= d22.DELEGESIZ_MUTLAK_TAVAN

    def test_envanter_olculen_kumeyle_birebir(self):
        """Envanter ne eksik ne fazla: ölçülen küme ile ÖZDEŞ olmalı."""
        _, olculen = d22._iddiasiz_test_nufusu(delegasyon=False,
                                               nitelikli=True)
        fazla = sorted(set(d22.DELEGESIZ_ENVANTERI) - set(olculen))
        eksik = sorted(set(olculen) - set(d22.DELEGESIZ_ENVANTERI))
        assert not fazla and not eksik, (
            'envanter ile ölçüm ayrışmış — envanterde fazla: %s / eksik: %s'
            % (fazla, eksik))

    def test_anahtar_nitelemesi_yuk_tasiyor(self):
        """Niteliksiz ``dosya::ad`` anahtarı ÖLÇÜLEN belirsizliği taşır.

        ``tests/fea/test_yapisal_vaka_dogrulama.py`` içinde
        ``TestVakaLameSI`` ve ``TestVakaAnsysVM25`` üç test adını paylaşır;
        niteliksiz anahtarla tek satır iki ayrı testi "kapsıyor" görünür ve
        biri silinse bayatlık kapısı susar. Bu iddia sayıyı değil İLİŞKİYİ
        ölçer: nitelenmiş küme, nitelenmemiş kümeden KESİN BÜYÜK olmalı.
        """
        _, nitelikli = d22._iddiasiz_test_nufusu(delegasyon=False,
                                                 nitelikli=True)
        _, duz = d22._iddiasiz_test_nufusu(delegasyon=False)
        assert len(set(nitelikli)) == len(nitelikli), (
            'nitelikli anahtarlar tekil değil: %d kalem, %d benzersiz'
            % (len(nitelikli), len(set(nitelikli))))
        assert len(set(nitelikli)) > len(set(duz)), (
            'niteleme yük taşımıyor görünüyor (%d nitelikli, %d düz) — '
            'ölçüt bozulmuş olabilir'
            % (len(set(nitelikli)), len(set(duz))))

    def test_sinifi_paylasan_adlar_ayri_kalemler(self):
        """Paylaşılan üç ad iki sınıf için AYRI AYRI envanterde."""
        paylasilan = ('test_radyal_gerilme_profili',
                      'test_cember_gerilme_profili',
                      'test_radyal_yer_degistirme')
        dosya = 'tests/fea/test_yapisal_vaka_dogrulama.py'
        for ad in paylasilan:
            sahipler = sorted(
                k.split('::')[1] for k in d22.DELEGESIZ_ENVANTERI
                if k.startswith(dosya + '::') and k.endswith('::' + ad))
            assert len(sahipler) == 2, (
                '%s için envanterde %d sınıf var (2 bekleniyor): %s'
                % (ad, len(sahipler), sahipler))

    def test_gerekceler_kredi_kaynagini_anmayi_surduruyor(self):
        """Gerekçe–kredi ilişkisi d22'de kilitli; burada çaprazlanır."""
        kopuk = []
        for anahtar, gerekce in sorted(d22.DELEGESIZ_ENVANTERI.items()):
            _, tablo, dugum = d22._envanter_dugumu(anahtar)
            assert dugum is not None, '%s çözülemedi' % anahtar
            kaynaklar = d22._kredi_kaynaklari(dugum, tablo)
            if not any(ad in gerekce for ad in kaynaklar):
                kopuk.append((anahtar, kaynaklar))
        assert not kopuk, (
            'gerekçe kredi kaynağını anmıyor: %s' % kopuk[:5])
