"""ÖH Dalga-19 · kulvar KATI · aşama 1 bekçileri.

Kapsanan kalemler
-----------------
P2B4-09  Grafit erozyon bandı kendi künyesiyle çelişiyordu: aynı kayıt
         (0.05, 0.15) tuple'ı, künyesinde 0.05-0.25 mm/s ve modül başlığında
         yine 0.05-0.25 diyordu; 'bandın konservatif üst ucu' diye
         etiketlenen varsayılan (0.15) künyesinin üst ucunun %60'ıydı ve
         katı motor, künyedeki bandın İÇİNDE kalan bir kullanıcı
         katsayısına (0.20 mm/s) 'bant dışı' uyarısı basıyordu.

Mevcut bekçilerin neden yakalayamadığı ham raporda (P2B4-09 'Bekçi
boşluğu'): tests/test_erosion.py::test_default_is_conservative_band_upper_end
AYNI KAYDIN İKİ ALANINI karşılaştırıyordu, kaydın kendi künyesiyle çaprazı
kurmuyordu; ::test_describe_is_json_friendly yalnız künyenin BOŞ OLMADIĞINA
bakıyordu.
"""
import re

import pytest

from hrma.analysis import transient_ballistics as tb
from hrma.analysis.transient_ballistics import (
    THROAT_EROSION_MATERIALS, ThroatErosionModel)


# "0.05-0.25 mm/s" biçimindeki sayısal bant beyanları (metin içinde).
_BANT_RE = re.compile(r'(\d+\.\d+)\s*-\s*(\d+\.\d+)\s*mm/s')


def _metindeki_bantlar(metin):
    return {(float(a), float(b))
            for a, b in _BANT_RE.findall(metin.replace('–', '-'))}


class TestGrafitBandiKunyesiyleCelismez:
    """Yayımlanan bant, kaydın KENDİ künyesindeki sayılarla aynı olmalı."""

    def test_kayit_bandi_kendi_kunyesindeki_sayilarla_ayni(self):
        rec = THROAT_EROSION_MATERIALS['graphite']
        bant = tuple(float(x) for x in rec['a_ref_band_mm_s'])
        kunye_bantlari = _metindeki_bantlar(rec['source'])
        assert kunye_bantlari, (
            "grafit künyesi sayısal bant içermiyor: bant atfedilemez")
        assert kunye_bantlari == {bant}, (
            f"kayıt bandı {bant} ⟷ künyedeki bant(lar) {kunye_bantlari}: "
            "aynı sözlük iki farklı bant söylüyor")

    def test_bant_geisler_kunyesinin_bagimsiz_transkripsiyonu(self):
        """ALTIN DEĞER: künyedeki bandın literatürden transkripsiyonu.

        Aşağıdaki (0.069, 0.353) bu testin BAĞIMSIZ transkripsiyonudur —
        ürün sabitinden ithal EDİLMEZ. Kaynak: Thakre & Yang, J. Prop.
        Power 24(4) 2008, Tablo 8 — Geisler'in (JANNAF Rocket Nozzle
        Technology Subcommittee Meeting, 1978) BATES motorunda ölçtüğü
        bulk grafit gerileme hızları, p_t = 6,9 MPa, %15..%27 Al AP/HTPB:
        0,353 / 0,284 / 0,200 / 0,124 / 0,069 mm/s.

        ÖH D27/OH-D25-27 (2026-09-08) — GÜNCELLENDİ: eski altın değer
        (0.05, 0.25) deponun KENDİ dizgesiydi; literatür notu
        (docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md §3)
        ölçülen bandın 0,069-0,353 olduğunu ve deponun üst ucunun
        ölçülenin %70,8'i kaldığını (erozyonu EKSİK, itki/basıncı FAZLA
        gösteren güvensiz yön) belgeledi. Künye hatası da düzeltildi:
        kaynağın yayım yeri AIAA değil JANNAF'tır.
        Tabanda (60cd341) ürün (0.05, 0.15) yayımlıyordu → KIRMIZI.
        """
        rec = THROAT_EROSION_MATERIALS['graphite']
        assert tuple(float(x) for x in rec['a_ref_band_mm_s']) == (0.069,
                                                                  0.353)
        assert 'Geisler' in tb.GRAPHITE_A_REF_BAND_CITATION
        assert 'JANNAF' in tb.GRAPHITE_A_REF_BAND_CITATION
        assert 'AIAA' not in tb.GRAPHITE_A_REF_BAND_CITATION, (
            "Geisler 1978 JANNAF'ta yayımlandı; künye AIAA diyemez")
        assert rec['a_ref_default_mm_s'] == pytest.approx(0.353, rel=1e-12)

    def test_modul_metninde_celisen_ikinci_bant_yok(self):
        """Modülün HİÇBİR yerinde çelişen ikinci bir sayısal bant olamaz."""
        kaynak = open(tb.__file__, encoding='utf-8').read()
        bant = tuple(float(x) for x in
                     THROAT_EROSION_MATERIALS['graphite']['a_ref_band_mm_s'])
        metin_bantlari = _metindeki_bantlar(kaynak)
        assert metin_bantlari, "modülde hiç sayısal bant beyanı yok"
        assert metin_bantlari == {bant}, (
            f"modül metninde {metin_bantlari} bandı/bantları geçiyor ama "
            f"kayıt {bant} yayımlıyor")

    def test_varsayilan_gercekten_kunyeli_bandin_ust_ucu(self):
        """'Konservatif üst uç' iddiası KÜNYEYE göre de doğru olmalı."""
        rec = THROAT_EROSION_MATERIALS['graphite']
        kunye_bandi = next(iter(_metindeki_bantlar(rec['source'])))
        assert rec['a_ref_default_mm_s'] == pytest.approx(
            kunye_bandi[1], rel=1e-12), (
            f"varsayılan {rec['a_ref_default_mm_s']} künyeli bandın üst ucu "
            f"{kunye_bandi[1]} değil (oran "
            f"{rec['a_ref_default_mm_s'] / kunye_bandi[1]:.2f})")
        assert ThroatErosionModel.for_material('graphite').rate_mm_s(
            70.0) == pytest.approx(kunye_bandi[1], rel=1e-12)

    def test_varsayilan_elle_yazilamaz_banttan_turetilir(self):
        """TEK KAYNAK: varsayılan bandın üst ucundan üretilir.

        Kaynak metninde 'a_ref_default_mm_s': <sayı> biçiminde elle yazılmış
        bir varsayılan kalırsa bant ile varsayılan yeniden ayrışabilir.
        """
        kaynak = open(tb.__file__, encoding='utf-8').read()
        elle = re.findall(r"'a_ref_default_mm_s':\s*([0-9.]+|None)", kaynak)
        assert elle == [], (
            f"a_ref_default_mm_s elle yazılmış: {elle} — bandın üst ucundan "
            "türetilmeli (ikinci literal ayrışmaya kapı açar)")
        # ÖH D27: çapa da elle yazılamaz (band yoksa varsayılanı O verir).
        capa_elle = re.findall(r"'a_ref_anchor_mm_s':\s*([0-9.]+|None)",
                               kaynak)
        assert capa_elle == [], (
            f'a_ref_anchor_mm_s elle yazılmış: {capa_elle} — künyeden '
            'türetilmeli')
        for anahtar, rec in THROAT_EROSION_MATERIALS.items():
            bant = rec.get('a_ref_band_mm_s')
            capa = rec.get('a_ref_anchor_mm_s')
            if bant:
                beklenen = float(bant[1])
            elif capa:
                beklenen = float(capa)
            else:
                beklenen = None
            assert rec['a_ref_default_mm_s'] == beklenen, anahtar


class TestBandinAtifDurumuSaklanmaz:
    """Bandı hiçbir kaynağa atfedilemeyen malzeme bunu SÖYLER."""

    def test_grafit_bandi_atfedilmis_ve_kunyesi_yayimlaniyor(self):
        d = ThroatErosionModel.for_material('graphite').describe()
        assert d['band_attributed'] is True
        assert d['band_source']
        assert _metindeki_bantlar(d['band_source']) == {
            tuple(float(x) for x in d['a_ref_band_mm_s'])}

    def test_cc_bandi_atfedilmemis_oldugunu_soyluyor(self):
        """C-C'nin yayımlanmış BANDI yok; bu gizlenmez.

        D19'daki hâli: kaynaksız (0.02, 0.10) bandı duruyordu, yalnız
        durumu alan adıyla söyleniyordu. ÖH D27/OH-D24-11 (b) o beyanın
        yetmediğini ölçtü (Doktrin 1: beyan çözüm değildir) — kaynaksız
        sayı SÖKÜLDÜ. Artık C-C hiç band yayımlamaz; katsayısı depodaki
        TEK atfedilebilir C-C ölçümüne (Borie ve ark., Thakre & Yang 2008
        Tablo 5 / Şekil 18) çapalıdır ve bu çapa adıyla yayımlanır.
        """
        d = ThroatErosionModel.for_material('carbon_carbon').describe()
        assert d['band_attributed'] is False
        assert d['band_source'] is None
        assert d['a_ref_band_mm_s'] is None, (
            'C-C için yayımlanmış bant yoktur; depo-içi kestirim bant '
            'diye yayımlanamaz')
        assert _metindeki_bantlar(d['source']) == set(), (
            "C-C künyesi sayısal bant veriyorsa band_attributed True olmalı")
        # Katsayı kaynaksız DEĞİL: çapası atfedilmiş ve künyeli.
        assert d['anchor_attributed'] is True
        assert d['anchor_source'] and 'Borie' in d['anchor_source']
        assert 'single measured' in d['anchor_source'].lower()


class TestKatiBantDisiUyarisiKunyeliBandaGore:
    """Künyeli bandın İÇİNDEKİ katsayı 'bant dışı' sayılamaz."""

    @staticmethod
    def _kodlar(a_ref):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        e = SolidRocketEngine(
            grain_type='bates', propellant_type='apcp', chamber_diameter=100,
            grain_length=500, core_diameter=30, chamber_pressure=40,
            overrides={'nozzle_throat_material': 'graphite',
                       'throat_erosion_a_ref_mm_s': a_ref})
        r = e.calculate_performance()
        return [w.get('code') for w in (r.get('warnings') or [])
                if isinstance(w, dict)]

    # ÖH D27/OH-D25-27: parametreler ölçülen banda (0.069-0.353) taşındı.
    # Eski liste 0.05'i "bant içi" sayıyordu; o sayı ölçülen en düşük
    # gerileme hızının (0.069) ALTINDADIR ve artık uyarı alır (aşağıda).
    @pytest.mark.parametrize('a_ref', [0.069, 0.15, 0.25, 0.353])
    def test_kunyeli_bandin_icindeki_katsayi_bant_disi_degil(self, a_ref):
        bant = tb.GRAPHITE_A_REF_BAND_MM_S
        assert bant[0] <= a_ref <= bant[1], 'parametre bandın içinde değil'
        assert 'warn.solid.throat_erosion_coeff_off_band' not in \
            self._kodlar(a_ref), (
            f"a_ref={a_ref} mm/s künyeli Geisler bandının {bant} "
            "içinde ama 'bant dışı' uyarısı basılıyor")

    def test_bandin_disindaki_katsayi_hala_uyari_aliyor(self):
        """Kapı gevşetilmedi: bandın gerçekten dışı hâlâ uyarı alır."""
        assert 'warn.solid.throat_erosion_coeff_off_band' in \
            self._kodlar(0.60)

    @pytest.mark.parametrize('a_ref', [0.05, 0.06])
    def test_olculen_bandin_altindaki_katsayi_artik_kaciyor_degil(self,
                                                                  a_ref):
        """ÖH D27/OH-D25-27: bandın ALT ucu da literatüre çapalandı.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/kati/a1/once.json →
        sonra.json): tabanda 0,05 ve 0,06 mm/s ölçülen bandın altında
        olmalarına rağmen SESSİZ geçiyordu (kacan_sayisi = 2), çünkü
        deponun bandı 0,05'ten başlıyordu. Ölçülen alt uç 0,069'dur.
        """
        assert a_ref < tb.GRAPHITE_A_REF_BAND_MM_S[0]
        assert 'warn.solid.throat_erosion_coeff_off_band' in \
            self._kodlar(a_ref), (
            f'a_ref={a_ref} mm/s ölçülen bandın altında ama sessiz geçti')


# --- ÖH D25 EKİ (Fable-D19 ŞARTI, P2B4-09 1. madde) ------------------------
class TestKullaniciKatsayisiYoluAtfiTasir:
    """Kullanıcı kendi a_ref'ini verse bile bandın ATFI yanıtta durur.

    Fable-D19 ölçümü: bu yol (solid_rocket_engine.py `_throat_erosion_model`,
    ``band_source``/``band_attributed`` aktarımı) BEKÇİSİZDİ — M3 mutasyonu
    (``band_attributed=False`` sabitlendi) üç dosyada 34 passed / 3 xfailed
    üretti, tek kırmızı yok. Ayrıntılı kardeş bekçi:
    tests/test_d25_kati_a1.py::TestP2B409KullaniciKatsayisiYolu
    """

    @staticmethod
    def _model(malzeme):
        import contextlib
        import io as _io

        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        with contextlib.redirect_stdout(_io.StringIO()), \
                contextlib.redirect_stderr(_io.StringIO()):
            m = SolidRocketEngine(
                grain_type='bates', propellant_type='apcp',
                chamber_diameter=100, grain_length=500,
                core_diameter=30, chamber_pressure=40,
                overrides={'nozzle_material': malzeme,
                           'throat_erosion_a_ref_mm_s': 0.20})
            return m._throat_erosion_model().describe()

    def test_grafitte_atif_tasinir(self):
        d = self._model('graphite')
        assert d['a_ref_mm_s'] == pytest.approx(0.20)
        assert d['band_attributed'] is True
        assert d['band_source'] == tb.GRAPHITE_A_REF_BAND_CITATION

    def test_karbon_karbonda_atif_yok_diye_beyan_edilir(self):
        d = self._model('carbon_carbon')
        assert d['material'] == 'carbon_carbon'
        assert d['band_attributed'] is False
        assert d['band_source'] is None
