"""Sürüm notlarının dile duyarlı kırpılması (v2.6.26 bekçisi).

Kapatılan kusur: `update_checker` sürüm notu gövdesini TEK PARÇA `[:4000]`
kırpıyordu. v2.6.26'nın canlı GitHub gövdesi 16045 karakterdi ve
`<!--HRMA-LANG:tr-->` imi 8072. karakterde başlıyordu — yani Türkçe bölüm
istemciye HİÇ ulaşmıyordu ve Türkçe arayüzde "Güncellemek ister misiniz?"
sorusunun altındaki not İngilizce çıkıyordu.

Geri gelirse bu dosya kırılır.
"""

from hrma.utils.update_checker import (
    NOTES_MAX_CHARS,
    clip_notes,
    split_notes_by_language,
)


def _iki_dilli_govde(en_uzunluk=None, tr_uzunluk=None):
    """Gerçek vakayı taklit eder: TR imi SINIRIN ötesinde başlar.

    2026-08-03: uzunluklar eskiden 8000'e sabitlenmişti, çünkü sınır 4000'di.
    Sınır 16000'e çıkınca kurgunun ÖNCÜLÜ çöktü (8072 > 16000 yanlış) ve test
    bir kusuru değil kendi eski varsayımını sınar oldu. Artık uzunluklar
    sınırdan türüyor: kurgu, sınır ne olursa olsun "TR imi sınırın ötesinde"
    koşulunu sağlar.
    """
    if en_uzunluk is None:
        en_uzunluk = NOTES_MAX_CHARS + 2000
    if tr_uzunluk is None:
        tr_uzunluk = NOTES_MAX_CHARS + 2000
    en = "# HRMA v2.6.26 — Quality release\nEN icerik satiri.\n" + "E" * en_uzunluk
    tr = "# HRMA v2.6.26 — Kalite sürümü\nTR içerik satırı.\n" + "T" * tr_uzunluk
    return "<!--HRMA-LANG:en-->\n%s\n<!--HRMA-LANG:tr-->\n%s" % (en, tr)


class TestDilBolme:
    def test_imlerden_bolunur(self):
        bolumler = split_notes_by_language(_iki_dilli_govde())
        assert set(bolumler) == {"en", "tr"}
        assert "Quality release" in bolumler["en"]
        assert "Kalite sürümü" in bolumler["tr"]

    def test_tek_dilli_govde_bolunmez(self):
        assert split_notes_by_language("# HRMA v2.6.0\nsadece tek dil") == {}

    def test_bos_govde(self):
        assert split_notes_by_language("") == {}
        assert split_notes_by_language(None) == {}


class TestKirpma:
    def test_turkce_bolum_kirpmada_dusmez(self):
        """Asıl kusur buydu: TR bölümü SINIRIN ötesinde başlıyor."""
        govde = _iki_dilli_govde()
        assert govde.index("<!--HRMA-LANG:tr-->") > NOTES_MAX_CHARS

        kirpilmis = clip_notes(govde)
        assert "Kalite sürümü" in kirpilmis, (
            "Türkçe bölüm kırpmada düştü — tek parça kırpma geri gelmiş olabilir"
        )
        assert "Quality release" in kirpilmis

    def test_her_bolum_ayri_sinirlanir(self):
        govde = _iki_dilli_govde(en_uzunluk=NOTES_MAX_CHARS + 5000,
                                 tr_uzunluk=NOTES_MAX_CHARS + 5000)
        for kod, metin in split_notes_by_language(clip_notes(govde)).items():
            assert len(metin) <= NOTES_MAX_CHARS, kod

    def test_imler_korunur(self):
        """İstemci (update_check.js) imlerden bölüyor; kırpma onları yutmamalı."""
        kirpilmis = clip_notes(_iki_dilli_govde())
        assert "<!--HRMA-LANG:en-->" in kirpilmis
        assert "<!--HRMA-LANG:tr-->" in kirpilmis

    def test_tek_dilli_govde_eskisi_gibi_kirpilir(self):
        """Tek dilli gövde de sınırlanır.

        Eşitlik DEĞİL "<=" sınanır: kırpma artık satır/boşluk sınırına geri
        sarıyor ve "kısaltıldı" beyanı ekliyor, yani sonuç sınırın tam
        üstünde durmaz (2026-08-03, sessiz kırpma düzeltmesi).
        """
        uzun = "x" * (NOTES_MAX_CHARS + 5000)
        kirpik = clip_notes(uzun)
        assert len(kirpik) <= NOTES_MAX_CHARS
        assert len(kirpik) > NOTES_MAX_CHARS * 0.5, 'kırpma metni yok etmiş'
        assert len(clip_notes("x" * 10)) == 10, 'sınır altı gövde kırpılmamalı'

    def test_imsiz_iki_dilli_govde_basliktan_bolunur(self):
        """Atom yedek yolu: GitHub HTML yorum satırı taşımaz (ölçüldü: im 0)."""
        govde = (
            "# HRMA v2.6.26 — Quality release\n" + "E" * 6000 +
            "\n# HRMA v2.6.26 — Kalite sürümü\n" + "T" * 6000
        )
        assert "Kalite sürümü" in clip_notes(govde)


class TestUcNoktaSozlesmesi:
    def test_check_for_update_dile_ayrilmis_alan_uretir(self, monkeypatch):
        """update_check.js `info['notes_' + lang]` okuyor; sunucu üretmeli."""
        from hrma.utils import update_checker as uc

        monkeypatch.setattr(uc, "_fetch_latest_release", lambda: {
            "tag_name": "v999.0.0",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/berketez/HRMA/releases/tag/v999.0.0",
            "assets": [],
            "body": _iki_dilli_govde(),
        })
        with uc._cache_lock:
            uc._cache["result"] = None
            uc._cache["checked_at"] = 0.0

        sonuc = uc.check_for_update(force=True)
        assert sonuc["available"] is True
        assert "Kalite sürümü" in sonuc["notes_tr"]
        assert "Quality release" in sonuc["notes_en"]
        assert len(sonuc["notes_tr"]) <= NOTES_MAX_CHARS

        with uc._cache_lock:
            uc._cache["result"] = None
            uc._cache["checked_at"] = 0.0
