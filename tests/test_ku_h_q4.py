"""Kitap uyum — hızlı düzeltmeler, kulvar q4 (katı + hibrit) bekçileri.

Kaynak: docs/arastirma/2026-10-05/notlar/KARS-S/kitap_uyum_girdisi.md
(H-7, KU-K2, KU-K4, KC-5/§17 K13). Rapor: docs/scofield/raw/OH/KU/h-q4/.

Bu dosyadaki bekçilerin hiçbiri YAYIMLANAN BİR SAYIYI kilitlemez; künye,
yorum, beyan ve fail-closed girdi çözümünü kilitler. Sayısal sabitler
(MC 1σ bantları, flooding eşiği) yalnız "DEĞİŞMEDİ" iddiası için okunur —
değerleri tek tanım noktalarından alınır, burada yeniden yazılmaz.
"""

import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRM = ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py'
HRE = ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py'
TB = ROOT / 'hrma' / 'analysis' / 'transient_ballistics.py'
UNC = ROOT / 'hrma' / 'analysis' / 'uncertainty.py'


def _oku(yol):
    return yol.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# KU-K2 — katı künyeleri
# ---------------------------------------------------------------------------
#: Düzeltilen ESKİ künye biçimleri. Herhangi biri geri gelirse künye yine
#: yanlış belgeye gider (SP-8089 = sıvı enjektör monografı; SP-8064'te
#: BATES geometrisi, segment boyu ve "Grain Design" başlığı yok).
ESKI_KATI_KUNYELERI = (
    'Böl. 12; NASA SP-8089',
    'Denk. 12-6; NASA SP-8089',
    "Ch. 12; NASA SP-8089.'",
    '# NASA SP-8064 "Solid Propellant Grain Design and Internal Ballistics".',
    '# Kaynak: NASA SP-8064 BATES nötrlük analizi',
    'Varsayılanlar motorun eski, NASA SP-8064',
    'L_seg ≈ D_chamber (NASA SP-8064)',
    '(NASA SP-8064 / Sutton BATES geometrisi)',
)


class TestKatiKunyeleri:
    def test_eski_kunye_bicimleri_kaynakta_yok(self):
        kaynak = _oku(SRM)
        geri_gelen = [k for k in ESKI_KATI_KUNYELERI if k in kaynak]
        assert not geri_gelen, f'eski künye geri geldi: {geri_gelen}'

    def test_grain_design_basligi_yalniz_sp8076_ile(self):
        """"Solid Propellant Grain Design and Internal Ballistics" SP-8076'dır."""
        satirlar = _oku(SRM).splitlines()
        for i, satir in enumerate(satirlar):
            if 'Solid Propellant Grain Design and Internal Ballistics' in satir:
                pencere = ' '.join(satirlar[max(0, i - 1):i + 1])
                assert 'SP-8076' in pencere, (i + 1, satir)

    def test_denge_basinci_kunyesi_sp8039_es44(self):
        kaynak = _oku(SRM)
        # docstring, iki yorum ve ürün metni: dördü de eş. (44)'e gider
        assert kaynak.count('eş. (44), s. 56') >= 3
        assert "NASA SP-8039, eq. (44), '" in kaynak

    def test_urun_metni_sp8089_yayimlamiyor(self):
        """Boğaz boyutlandırma ürün metni denge basıncını SP-8039'a bağlar.

        Yanıtın başka yerlerinde SP-8089 MEŞRU olarak geçer (sıvı enjektör /
        chug künyesi); bekçi yalnız tepe-Kn boyutlandırma metnine bakar.
        """
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            sonuc = SolidRocketEngine().calculate_performance()
        bulunan = []

        def _gez(d):
            if isinstance(d, dict):
                for v in d.values():
                    _gez(v)
            elif isinstance(d, (list, tuple)):
                for v in d:
                    _gez(v)
            elif isinstance(d, str) and 'peak-Kn criterion' in d:
                bulunan.append(d)
        _gez(sonuc)
        assert bulunan, 'tepe-Kn boyutlandırma metni yanıtta yok'
        for metin in bulunan:
            assert 'SP-8089' not in metin
            assert 'NASA SP-8039, eq. (44), p. 56' in metin

    def test_kutle_dengesi_depolama_ihmali_beyanli(self):
        """§17 K13 / KC-5: ρ_g ve d(ρ_g·V)/dt ihmali yorumda beyanlı."""
        kaynak = _oku(SRM)
        assert 'ρ_p − ρ_g' in kaynak
        assert 'SP-8076 eş. (35), s. 54' in kaynak
        assert 'SP-8039 eş. (47)' in kaynak


class TestKatiMCBantlari:
    def test_mc_bantlari_degismedi_kunye_sinirini_soyler(self):
        from hrma.engines.solid_rocket_engine import SOLID_MC_TOLERANCE_MODEL
        from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS
        katı = DEFAULT_UQ_MODELS['solid']
        # İki tanım noktası aynı sayıyı taşıyor (değer DEĞİŞMEDİ)
        assert (katı['burn_rate_a'].sigma
                == SOLID_MC_TOLERANCE_MODEL['burn_rate_a_rel_sigma'])
        assert (katı['burn_rate_n_delta'].sigma
                == SOLID_MC_TOLERANCE_MODEL['burn_rate_n_abs_sigma'])
        assert (katı['density'].sigma
                == SOLID_MC_TOLERANCE_MODEL['density_rel_sigma'])
        assert (katı['c_star'].sigma
                == SOLID_MC_TOLERANCE_MODEL['c_star_rel_sigma'])
        basis = SOLID_MC_TOLERANCE_MODEL['basis']
        assert 'SP-8064' in basis and 'LIMIT of 2%' in basis

    def test_uncertainty_sp8064_kunyesi_dogru_iddiada(self):
        from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS
        katı = DEFAULT_UQ_MODELS['solid']
        notlar = {k: v.source_note for k, v in katı.items()}
        assert all('+/-1-3%' not in n for n in notlar.values())
        assert 'LIMIT of 2%' in notlar['burn_rate_a']
        for ad in ('burn_rate_n_delta', 'density', 'c_star'):
            assert 'assumed' in notlar[ad], ad
        # Hiçbir not bir bandı SP-8064'e "kaynak" diye bağlamaz:
        # eski biçim "(NASA SP-8064, 1971)." ile biten nottu.
        assert all(not n.rstrip().endswith('(NASA SP-8064, 1971).')
                   for n in notlar.values())


# ---------------------------------------------------------------------------
# H-7 — hibrit akı tabanı, ölü girdi, transient yorumu
# ---------------------------------------------------------------------------
class TestHibritAkiTabani:
    @staticmethod
    def _motor(**kw):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return HybridRocketEngine(**kw)

    @pytest.mark.parametrize('ham, beklenen', [
        ('ox', 'ox'), ('OX', 'ox'), (' ox ', 'ox'), ('Ox', 'ox'),
        ('total', 'total'), ('TOTAL', 'total'), ('', 'ox'),
    ])
    def test_dize_girdi_tek_cozucuden_gecer(self, ham, beklenen):
        assert self._motor(flux_mode=ham).flux_mode == beklenen

    @pytest.mark.parametrize('ham', ['G_ox', 'oxidizer', 'G_total', 123])
    def test_taninmayan_girdi_reddedilir(self, ham):
        """Sessiz 'total' düşüşü yok (fail-closed)."""
        from hrma.analysis.regression_analysis import UnresolvedFluxMode
        with pytest.raises(UnresolvedFluxMode):
            self._motor(flux_mode=ham)

    def test_varsayilan_ox(self):
        assert self._motor().flux_mode == 'ox'

    def test_none_eski_yedegi_korur_beyanli(self):
        """None → 'total' eski yedek; yorumda devir olarak beyanlı.

        Bu bir ONAY değil, kayıttır: yedek DEFAULT_FLUX_MODE ('ox') ile
        çelişir ve tests/test_d29_arayuz_panel_a2.py ifadeyi kilitlediği için
        bu kulvarda çevrilmedi. Çevrildiği gün bu test de çevrilir.
        """
        assert self._motor(flux_mode=None).flux_mode == 'total'
        assert 'devir listesinde' in _oku(HRE)

    def test_curuk_yorumlar_geri_gelmez(self):
        kaynak = _oku(HRE)
        assert "G_total = G_ox + G_fuel (VARSAYILAN); 'ox' = eski" \
            not in kaynak
        assert "Yalnız G_ox kullanmak (eski kod)" not in kaynak
        assert "flux_mode='ox' verilirse eski davranış (geriye uyum)" \
            not in kaynak


class TestHibritOluGirdi:
    @staticmethod
    def _motor(**kw):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return HybridRocketEngine(**kw)

    def test_verilen_deger_kullanilmadigini_soyler(self):
        e = self._motor(throat_erosion_rate=1e-4)
        kayit = [g for g in e.design_gate_checks
                 if g.get('gate') == 'throat_erosion_rate_input']
        assert len(kayit) == 1
        assert kayit[0]['status'] == 'not_coupled'
        assert kayit[0]['applied'] is False
        assert kayit[0]['value'] == pytest.approx(1e-4)

    @pytest.mark.parametrize('deger', [None, 0.0])
    def test_verilmezse_kayit_yok(self, deger):
        e = self._motor(throat_erosion_rate=deger)
        assert not [g for g in e.design_gate_checks
                    if g.get('gate') == 'throat_erosion_rate_input']

    def test_beyan_dogru_kalir_kimse_okumuyor(self):
        """"Çözüme bağlı değil" beyanı ancak kimse okumadıkça doğrudur.

        Girdi bir gün bağlanırsa (KC-9 kararı) bu bekçi kırmızı olur ve
        beyan + hüküm kaydı birlikte kaldırılır.
        """
        okuyan = []
        for yol in (ROOT / 'hrma').rglob('*.py'):
            metin = yol.read_text(encoding='utf-8')
            if 'throat_erosion_rate' not in metin:
                continue
            if yol != HRE:
                okuyan.append(str(yol.relative_to(ROOT)))
                continue
            kod = [s for s in metin.splitlines()
                   if 'throat_erosion_rate' in s
                   and not s.lstrip().startswith('#')]
            izinli = (
                'throat_erosion_rate=None,',
                'if throat_erosion_rate is None:',
                'self.throat_erosion_rate = 0.0',
                'self.throat_erosion_rate = max(0.0, float(throat_erosion_rate))',
                'if (np.isfinite(self.throat_erosion_rate)',
                'and self.throat_erosion_rate > 0.0):',
                "'gate': 'throat_erosion_rate_input',",
                "'quantity': 'throat_erosion_rate',",
                "'value': float(self.throat_erosion_rate),",
                "'source': 'throat_erosion_rate (input you supplied)',",
            )
            okuyan += [s.strip() for s in kod if s.strip() not in izinli]
        assert not okuyan, f'throat_erosion_rate artık okunuyor: {okuyan}'


class TestTransientUssuYorumu:
    def test_modul_basligi_ve_uyarilar_08_demiyor(self):
        from hrma.analysis import transient_ballistics as tb
        assert '(Pc/70 bar)^0.8' not in (tb.__doc__ or '')
        assert 'Pc^0.8 oxidation model' not in _oku(TB)
        for ad in ('steel', 'copper'):
            uyari = tb.THROAT_EROSION_MATERIALS[ad]['warning']
            assert 'NOT RECOMMENDED' in uyari
            assert 'Pc^0.8' not in uyari
            # Denetim Ş-1: 0,8 üssü başka biçimde de geri gelemez (X5);
            # uyarı yasayı genel üs n ile anar.
            assert '0.8' not in uyari and '0,8' not in uyari, (ad, uyari)
            assert 'a_ref*(Pc/Pc_ref)^n' in uyari, (ad, uyari)
        # Denetim Ş-1 (X6): model cümlesi genel üs n ile yazılır. Başlıktaki
        # H-7 tarihçe notu eski "^0.8" dizgesini anar ama Pc_ref'e bağlı bir
        # 0,8 üssü yazmaz.
        doc = tb.__doc__ or ''
        assert 'ṙ = a_ref·(Pc/Pc_ref)^n' in doc
        assert not re.search(r'Pc_ref\)\s*\^\s*0[.,]8', doc)


# ---------------------------------------------------------------------------
# KU-K4 — flooding künyesi ve gerekçesi
# ---------------------------------------------------------------------------
class TestFloodingKunyesi:
    def test_kunye_sayiyi_sutton_a_baglamiyor(self):
        kaynak = _oku(HRE)
        i = kaynak.index('OX_FLUX_FLOODING_WARN_KG_M2S = ')
        blok = kaynak[max(0, i - 2500):i]
        assert "Bant: Sutton & Biblarz 9. baskı Böl. 16 — hibrit portta" \
            not in blok
        assert 'Fraters & Cervone' in blok
        assert '1370' in blok and 'SAYI VERMEZ' in blok

    def test_esik_degismedi(self):
        from hrma.engines import hybrid_rocket_engine as hre
        # 600 eşiği bu kulvarda DEĞİŞMEZ; tek tanım noktasındaki değer
        # ast ile kaynaktan okunur ve modül değeriyle karşılaştırılır.
        m = re.search(r'^OX_FLUX_FLOODING_WARN_KG_M2S = ([0-9.]+)$',
                      _oku(HRE), re.M)
        assert m and float(m.group(1)) == hre.OX_FLUX_FLOODING_WARN_KG_M2S
        assert hre.OX_FLUX_FLOODING_WARN_KG_M2S == 600.0
