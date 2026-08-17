# -*- coding: utf-8 -*-
"""Bebek-Scofield hibrit bekçileri (parti 31, A1) — F5-1 / F3-1 / F3-2 / F4-3.

Her test, sicildeki (docs/scofield-bebek-2026-08-17.md) ölçülmüş bir kusurun
KENDİSİNİ yakalar; kusur geri gelirse kırmızıya döner.

  F5-1 (kritik): ısı zinciri sessiz 0,005 m cidarla koşarken yapısal/CAD
      zinciri kendi boyutlandırdığı cidarı (ölçülen 18,79 mm) çiziyordu ve
      "çizilen cidarda SF" ısı zincirinin hiç görmediği bir cidara aitti.
      Sözleşme: cidarın TEK kaynağı vardır — kullanıcı verdiyse o, yoksa
      yapısal boyutlandırma; ısı zinciri onu TÜKETİR ve yol ADIYLA beyan
      edilir (chamber_wall_policy).
  F3-1: boğaz C_D=0,98 boyutlandırmaya gömülüyken thrust_curve basıncı
      C_D'siz geri okunuyordu (Pc[0] = 29,40 bar = 0,98 x 30,00). Sözleşme:
      debi C_D taşır (mdot = CD*Pc*At/c*) ve özdeşlik her istasyonda tutar.
  F3-2: total_mass_kg yanan yakıtla toplanıyordu (97,23 kg); yüklü kütle
      102,48 kg — %5,1'lik yanmayan sliver uçuş bütçesinden düşülüyordu.
  F4-3: thrust=0 sessizce 1000 N oluyordu ve yanıt supplied=['thrust']
      diyordu. input_guard sözleşmesi: yalnız None ve '' varsayılana düşer;
      0 beyanlı hatadır.
"""

import contextlib
import io
import warnings

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    HybridRocketEngine, THROAT_DISCHARGE_COEFFICIENT)


# Örnek motor: examples/'Example Hybrid N2O-HTPB 3kN.hrma' girdileri
# (sicildeki ölçümlerin tamamı bu motorla alındı).
ORNEK_3KN = dict(
    thrust=3000.0, burn_time=10.0, of_ratio=7.0, chamber_pressure=30.0,
    atmospheric_pressure=1.013, l_star=1.0, expansion_ratio=0,
    nozzle_type='conical', combustion_type='infinite',
    chamber_diameter_input=0, fuel_type='htpb', fuel_density=920,
    regression_a=3.68e-05, regression_n=0.555, oxidizer_type='n2o',
    injector_type='showerhead',
)


def _kos(**kwargs):
    """Motoru sessizce koşturur, (motor, sonuç) döndürür."""
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter('ignore')
        eng = HybridRocketEngine(**kwargs)
        return eng, eng.calculate()


def _kodlar(sonuc):
    return {w.get('code') for w in (sonuc.get('design_warnings') or [])
            if isinstance(w, dict)}


@pytest.fixture(scope='module')
def cidarsiz():
    """Cidar VERİLMEDEN koşan örnek motor (F5-1'in kritik yolu)."""
    return _kos(**ORNEK_3KN)


@pytest.fixture(scope='module')
def cidarli():
    """Kullanıcının AÇIKÇA 8 mm cidar verdiği koşu (yol A)."""
    return _kos(**ORNEK_3KN, wall_thickness=0.008)


# ---------------------------------------------------------------------------
# F5-1 — iki farklı kamara cidarı
# ---------------------------------------------------------------------------

class TestF51TekCidar:

    def test_isi_yapisal_ve_cad_ayni_cidari_kullanir(self, cidarsiz):
        """KUSURUN KENDİSİ: ısı 5,0 mm / yapısal-CAD 18,79 mm ayrışması.

        Sessiz 0,005 m varsayılanı geri gelirse ısı zincirinin cidarı
        yapısal cidardan kopar ve bu eşitlikler kırılır.
        """
        eng, res = cidarsiz
        isi_mm = float(
            res['heat_transfer_analysis']['design_parameters']
            ['wall_thickness'])
        ca = res['structural_analysis']['chamber_analysis']
        yapisal_mm = float(ca['wall_thickness_used_mm'])
        # Isı zincirinin tükettiği cidar = yapısal cidar (bit-eşitlik hedefi;
        # sabit nokta oturmazsa kalıntı beyanlıdır, tolerans o kalıntıdır).
        kalinti = res['chamber_wall_policy'].get('sizing_residual_rel') or 0.0
        assert isi_mm == pytest.approx(
            yapisal_mm, rel=max(kalinti, 1e-9)), (
            f'ısı zinciri {isi_mm} mm, yapısal zincir {yapisal_mm} mm — '
            f'aynı motorda iki cidar (F5-1 geri geldi)')
        # Motor niteliği ve lüle-malzeme değerlendirmesi de aynı sayıyı okur.
        assert eng.wall_thickness * 1000.0 == pytest.approx(yapisal_mm,
                                                            rel=1e-9)
        nm = res.get('nozzle_material_analysis') or {}
        if 'wall_thickness_mm' in nm:
            assert float(nm['wall_thickness_mm']) == pytest.approx(
                yapisal_mm, rel=1e-9)

    def test_cad_cizilen_cidar_ve_sf_ayni_parcaya_ait(self, cidarsiz):
        """'safety_factor_at_drawn_wall' ısı zincirinin GÖRDÜĞÜ cidara ait.

        Ölçülen kusur: ürün SF=2,152'yi 18,79 mm'lik çizilen cidar için
        yayımlıyordu ama o SF, ısı zincirinin 5 mm cidarından türeyen
        sıcaklıklarla hesaplanmıştı. Çizilen cidar kendi termal durumuyla
        değerlendirilince SF_total 0,941 ölçüldü — eski çift-cidar durumu
        tehlikeyi maskeliyordu.
        """
        from hrma.export.cad_visualization import _chamber_wall_design
        eng, res = cidarsiz
        tasarim = _chamber_wall_design(res)
        ca = res['structural_analysis']['chamber_analysis']
        assert tasarim['thickness_m'] is not None
        # Çizilen kalınlık = gerilmelerin hesaplandığı kalınlık
        assert tasarim['thickness_m'] * 1000.0 == pytest.approx(
            float(ca['wall_thickness_used_mm']), rel=1e-9)
        # Çizilen kalınlık = ısı zincirinin tükettiği kalınlık
        isi_mm = float(res['heat_transfer_analysis']['design_parameters']
                       ['wall_thickness'])
        assert tasarim['thickness_m'] * 1000.0 == pytest.approx(
            isi_mm, rel=1e-6)
        # CAD'in SF'i yapısal zincirin toplam SF'i ile aynı sayı
        assert tasarim['safety_factor'] == pytest.approx(
            float(ca['safety_factor_total']), rel=1e-9)

    def test_politika_beyani_sized(self, cidarsiz):
        """Cidar verilmeyince yol ADIYLA beyan edilir (sessiz seçim yok)."""
        eng, res = cidarsiz
        pol = res['chamber_wall_policy']
        assert pol['policy'] == 'sized_by_structural_analysis'
        assert pol['wall_thickness_m'] == pytest.approx(eng.wall_thickness,
                                                        rel=1e-12)
        assert pol['sizing_iterations'] >= 1
        assert 'basis' in pol and 'single' in pol['basis'].lower()
        # Boyutlandırma yolunda SF hedefin geri okunmasıdır; bunun beyanı
        # (totoloji bayrağı) korunur — hüküm kapısı (app.py) bunu okur.
        ca = res['structural_analysis']['chamber_analysis']
        assert ca['design_mode'] == 'size'
        assert ca['safety_factor_is_tautological'] is True

    def test_kullanici_cidari_kazanir(self, cidarli):
        """Yol A: kullanıcının 8 mm'si HEM ısı HEM yapısal zincire gider."""
        eng, res = cidarli
        pol = res['chamber_wall_policy']
        assert pol['policy'] == 'user_supplied'
        isi_mm = float(res['heat_transfer_analysis']['design_parameters']
                       ['wall_thickness'])
        ca = res['structural_analysis']['chamber_analysis']
        assert isi_mm == pytest.approx(8.0, rel=1e-9)
        assert float(ca['wall_thickness_used_mm']) == pytest.approx(
            8.0, rel=1e-9)
        assert ca['design_mode'] == 'verify'
        assert ca['safety_factor_is_tautological'] is False

    def test_aralik_disi_cidar_sessizce_5mm_olmaz(self):
        """500 mm girdi: uyarı + boyutlandırma yolu. Eski davranış BURADA
        yakalanır: aralık dışı değer sessizce 0,005 m'ye düşüyor ve üstelik
        'kullanıcı verdi' bayrağıyla 5 mm DOĞRULANMIŞ gibi raporlanıyordu."""
        eng, res = _kos(**ORNEK_3KN, wall_thickness=0.5)
        assert 'warn.hybrid.wall_thickness_out_of_range' in _kodlar(res)
        assert eng.wall_thickness_user_supplied is False
        pol = res['chamber_wall_policy']
        assert pol['policy'] == 'sized_by_structural_analysis'
        ca = res['structural_analysis']['chamber_analysis']
        # 0,5 mm'lik girdinin de, sessiz 5 mm'nin de izi olmamalı: cidar
        # boyutlandırmanın kendi sonucudur ve ısı zinciri onu okur.
        isi_mm = float(res['heat_transfer_analysis']['design_parameters']
                       ['wall_thickness'])
        assert isi_mm == pytest.approx(float(ca['wall_thickness_used_mm']),
                                       rel=1e-6)
        assert ca['design_mode'] == 'size'

    def test_gecersiz_cidar_uyarir_ve_boyutlandirmaya_duser(self):
        eng, res = _kos(**ORNEK_3KN, wall_thickness='kalin')
        assert 'warn.hybrid.wall_thickness_invalid' in _kodlar(res)
        assert res['chamber_wall_policy']['policy'] == \
            'sized_by_structural_analysis'


# ---------------------------------------------------------------------------
# F3-1 — tek C_D sözleşmesi
# ---------------------------------------------------------------------------

class TestF31TekCD:

    def test_thrust_curve_t0_tasarim_noktasi(self, cidarsiz):
        """KUSURUN KENDİSİ: Pc[0] tasarımın 0,98 katıydı (29,40 bar).

        Ölçülen (düzeltme sonrası): Pc[0] = 30,0 (tam), F[0] = 3000,0 (tam).
        C_D geri okumadan çıkarılırsa Pc[0]/tasarım = 0,98 olur ve bu
        tolerans (1e-6) %2'lik kaymayı anında yakalar.
        """
        eng, res = cidarsiz
        tc = res['thrust_curve']
        assert tc['pressure'][0] == pytest.approx(res['chamber_pressure'],
                                                  rel=1e-6)
        assert tc['thrust'][0] == pytest.approx(res['thrust'], rel=1e-6)

    def test_cd_ozdesligi_her_istasyonda(self, cidarsiz):
        """mdot = CD*Pc*At/c* özdeşliği thrust_curve'ün HER noktasında tutar.

        Diziler aynı seyreltme indeksiyle yayımlandığı için hizalıdır;
        ölçülen kalıntı 1,8e-16 (aynı aritmetik). 1e-9 toleransı C_D'nin
        geri okumadan düşmesini (kalıntı ~0,0204) net yakalar.
        """
        eng, res = cidarsiz
        tc = res['thrust_curve']
        cstar = res['of_shift_performance']['c_star']
        At = float(res['throat_area'])
        assert len(tc['mass_flow']) == len(tc['pressure']) == len(cstar)
        for i, (mdot, pc_bar, cs) in enumerate(
                zip(tc['mass_flow'], tc['pressure'], cstar)):
            beklenen = THROAT_DISCHARGE_COEFFICIENT * pc_bar * 1e5 * At / cs
            assert mdot == pytest.approx(beklenen, rel=1e-9), (
                f'istasyon {i}: mdot={mdot} != CD*Pc*At/c*={beklenen} — '
                f'C_D sözleşmesi kırıldı')

    def test_tank_blowdown_t0_tasarim_noktasi(self, cidarsiz):
        """Kabul ölçütünün öteki yarısı: blowdown serisi t=0'da tasarım
        noktasını verir (F=3000 N, Pc=30,00 bar). İtki tarafındaki düzeltme
        hrma/analysis/transient_ballistics.py'dedir (F = CF*Pc*(CD*At));
        bu bekçi iki dosyanın ORTAK sözleşmesini kilitler.
        """
        eng, res = cidarsiz
        bd = res['tank_blowdown']
        assert bd.get('status') == 'modelled', bd.get('reason')
        assert bd['thrust_N'][0] == pytest.approx(res['thrust'], rel=1e-3)
        assert bd['chamber_pressure_bar'][0] == pytest.approx(
            res['chamber_pressure'], rel=1e-3)

    def test_cd_sozlesmesi_iki_uc_ayni_sayi(self):
        """Boyutlandırma ucu (bu dosya) ile transient ucu aynı sayıyı taşır.

        İki sabit iki dosyada duruyor (dosya sahipliği bu partide ayrıktı;
        tek tanıma indirme ana modele bildirildi). Biri kayarsa itki/basınç
        serileri tasarım noktasından kopar — bu test onu erken yakalar.
        """
        from hrma.analysis.transient_ballistics import (
            NOZZLE_DISCHARGE_COEFFICIENT)
        assert THROAT_DISCHARGE_COEFFICIENT == NOZZLE_DISCHARGE_COEFFICIENT


# ---------------------------------------------------------------------------
# F3-2 — kütle bütçesi yüklenen değerle
# ---------------------------------------------------------------------------

class TestF32YuklenenKutle:

    def test_total_mass_yuklenen_butcedir(self, cidarsiz):
        """KUSURUN KENDİSİ: total_mass_kg yanan yakıtla toplanıyordu.

        Ölçülen: eski değer 97,2327 kg; yüklü gerçek 102,4798 kg
        (fark 5,247 kg = yanmayan sliver). Kural yanıtın kendi
        oxidizer_mass_basis alanında zaten yazılıydı: kütle bütçesi
        YÜKLENEN değeri kullanır.
        """
        eng, res = cidarsiz
        kd = res['design_summary']['key_dimensions']
        toplam = float(kd['total_mass_kg'])
        beklenen = (float(kd['dry_mass_estimate_kg'])
                    + float(res['oxidizer_mass'])
                    + float(res['fuel_mass_loaded']))
        assert toplam == pytest.approx(beklenen, rel=1e-9)
        # Sliver pozitifken yanan-yakıt toplamı ile AYRIŞMALI: eşitlerse
        # kusur geri gelmiş demektir.
        if float(res['fuel_mass_loaded']) > float(res['fuel_mass']):
            eski_yanlis = (float(kd['dry_mass_estimate_kg'])
                           + float(res['oxidizer_mass'])
                           + float(res['fuel_mass']))
            assert toplam > eski_yanlis + 1e-6

    def test_total_mass_basis_beyanli(self, cidarsiz):
        eng, res = cidarsiz
        kd = res['design_summary']['key_dimensions']
        temel = kd.get('total_mass_basis') or ''
        assert 'loaded' in temel.lower()
        assert 'sliver' in temel.lower()


# ---------------------------------------------------------------------------
# F4-3 — 0 ile "verilmedi" karıştırılmaz
# ---------------------------------------------------------------------------

class TestF43SifirGirdi:

    def _kur(self, **kw):
        with warnings.catch_warnings(), \
                contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter('ignore')
            return HybridRocketEngine(of_ratio=7.0, chamber_pressure=30.0,
                                      fuel_type='htpb', oxidizer_type='n2o',
                                      **kw)

    def test_sifir_itki_beyanli_hata(self):
        """KUSURUN KENDİSİ: thrust=0 sessizce F=1000 N oluyordu."""
        with pytest.raises(ValueError, match="'thrust'.*positive"):
            self._kur(thrust=0, burn_time=10.0)

    def test_sifir_sure_beyanli_hata(self):
        with pytest.raises(ValueError, match="'burn_time'.*positive"):
            self._kur(thrust=3000.0, burn_time=0)

    def test_sifir_impuls_beyanli_hata(self):
        with pytest.raises(ValueError, match="'total_impulse'.*positive"):
            self._kur(total_impulse=0)

    def test_negatif_itki_beyanli_hata(self):
        with pytest.raises(ValueError, match="'thrust'.*positive"):
            self._kur(thrust=-3000.0, burn_time=10.0)

    def test_verilmedi_yer_tutucu_ve_beyanli(self):
        """None = verilmedi: yer tutucu (1000 N / 10 s) KALIR ama beyanlıdır
        ve supplied listesinde GÖRÜNMEZ (input_guard sözleşmesi)."""
        eng = self._kur()
        assert eng.F == 1000 and eng.t_b == 10
        assert 'thrust' in eng._defaults_used
        assert 'burn_time' in eng._defaults_used
        assert eng.impulse_input_resolution['supplied'] == []

    def test_bos_dize_verilmedi_sayilir(self):
        """'' input_guard'da None ile aynı muameleyi görür; supplied
        listesine 'kullanıcı verdi' diye yazılmaz (ölçülen ikinci yüz:
        supplied=['thrust'] yalanı)."""
        eng = self._kur(thrust='', burn_time=10.0)
        assert eng.F == 1000
        assert 'thrust' not in eng.impulse_input_resolution['supplied']
        assert 'thrust' in eng._defaults_used

    def test_sayi_olmayan_itki_beyanli_hata(self):
        with pytest.raises(ValueError, match="'thrust'"):
            self._kur(thrust='bol', burn_time=10.0)
