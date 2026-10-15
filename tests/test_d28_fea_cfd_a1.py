"""ÖH Dalga-28 · kulvar fea-cfd · aşama 1/2 — TEK KALEMLİK (üç kimlik).

Kalemler:
  * OH-Z5-02  — ``.motor.combustion_stability.lfi.frequency_paths_rel_diff``
                sabit yaprağının hükmü (D25'ten beri açık, son yaprak).
  * OH-D27-05 — köprünün inceltme sürücüsü YAYIMLANAN kipi de izlemeli.
  * OH-D27-06 — kanonik "hüküm kazanılan vaka" kaydı + onu KEŞFEDEN bekçi.

Kanıt dizini: ``docs/scofield/raw/OH/D28/fea-cfd/a1/``.
Her bekçi ters-mutasyonla kırmızı gösterildi (``mutasyon_a1.json``).
"""
import contextlib
import io
import json
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli

KOK = Path(__file__).resolve().parents[1]


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **k)


# ======================================================================
# OH-Z5-02 — iki frekans yolunun farkı TEK KAYNAKTAN, özdeşlik KAPIDA
# ======================================================================
class TestOHZ502TekKaynak:
    """Yaprak tanım gereği sabittir; sabitliği İDDİA değil, ÖLÇÜM."""

    #: Beş ayrı işletme noktası — yaprağın girdiden bağımsızlığı burada
    #: ölçülür (tabanda bu beş nokta ÜÇ AYRI sayı veriyordu).
    NOKTALAR = (
        dict(oxidizer_type='n2o', grain_length_m=0.60,
             chamber_pressure_Pa=3.0e6, oxidizer_flux_kg_m2_s=180.0,
             of_ratio=6.0),
        dict(oxidizer_type='n2o', grain_length_m=1.20,
             chamber_pressure_Pa=1.5e6, oxidizer_flux_kg_m2_s=90.0,
             of_ratio=3.0),
        dict(oxidizer_type='gox', grain_length_m=0.25,
             chamber_pressure_Pa=5.0e6, oxidizer_flux_kg_m2_s=420.0,
             of_ratio=2.2),
        dict(oxidizer_type='lox', grain_length_m=2.30,
             chamber_pressure_Pa=1.7e6, oxidizer_flux_kg_m2_s=455.7,
             of_ratio=7.9),
        dict(oxidizer_type='n2o', grain_length_m=0.83,
             chamber_pressure_Pa=2.4e6, oxidizer_flux_kg_m2_s=133.3,
             total_flux_kg_m2_s=310.7),
    )

    def test_yaprak_BES_NOKTADA_TEK_SAYI_ve_kardesiyle_BIT_AYNI(self):
        """Aynı büyüklük iki adla basılıyorsa AYNI SAYI olmak zorunda.

        TABAN ÖLÇÜMÜ (``once_z502.json``): satır içi float yolu
        ``abs(frequency*delay/0.48 - 1)`` beş noktada ÜÇ ayrı değer
        veriyordu (…646446 / …66865 / …679752) ve hiçbiri, aynı sözlükte
        duran ``coefficient_identity_residual_rel`` (…671426) ile bit-aynı
        değildi — üstelik yaprağın kendi künyesi ikisinin "exactly" aynı
        olduğunu söylüyordu. Oynayan şey ölçüm değil yuvarlama
        gürültüsüydü (yayılım ≈ 1,7e-13 bağıl).
        """
        from hrma.stability import hybrid_lfi as LFI
        degerler = set()
        for kw in self.NOKTALAR:
            r = LFI.assess_hybrid_lfi(**kw)
            assert (r['frequency_paths_rel_diff']
                    == r['coefficient_identity_residual_rel']), (
                'ürün AYNI büyüklüğü iki FARKLI sayı olarak basıyor: '
                f"{r['frequency_paths_rel_diff']!r} != "
                f"{r['coefficient_identity_residual_rel']!r}")
            assert (r['frequency_paths_rel_diff']
                    == LFI.LFI_FREQUENCY_PATHS_REL_DIFF)
            degerler.add(r['frequency_paths_rel_diff'])
        assert len(degerler) == 1, (
            'yaprak girdiye göre oynuyor ama bu bir ÖLÇÜM DEĞİL, float '
            f'gürültüsü: {sorted(degerler)!r}')

    def test_sabitin_SEBEBI_cebirsel_ozdeslik(self):
        """f·τ = K·c' — girdi sadeleşir; yaprak basım artığının kendisi."""
        from hrma.stability import hybrid_lfi as LFI
        beklenen = (abs(LFI.LFI_COEFFICIENT - LFI.LFI_COEFFICIENT_FROM_DELAY)
                    / LFI.LFI_COEFFICIENT_FROM_DELAY)
        assert LFI.LFI_FREQUENCY_PATHS_REL_DIFF == beklenen
        assert (LFI.LFI_FREQUENCY_PATHS_REL_DIFF
                == LFI.LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL), (
            'TEK KAYNAK kopmuş: yaprak artık ikinci bir yerden geliyor')

    def test_isletme_noktasi_ozdesligi_HER_KOSUMDA_olculuyor(self):
        """Sabitlik iddiası değil, kapı: sağlıklı noktada sapma ~0."""
        from hrma.stability import hybrid_lfi as LFI
        for kw in self.NOKTALAR:
            r = LFI.assess_hybrid_lfi(**kw)
            sapma = LFI.frekans_yollari_ozdeslik_kapisi(
                r['frequency_hz'], r['boundary_layer_delay_s'])
            assert abs(sapma) <= LFI.LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL
            # band dekoratif değil: ölçülen gürültü bandın çok altında
            assert abs(sapma) < 1e-12

    def test_ozdeslik_koparsa_HICBIR_SAYI_yayimlanmaz(self):
        """FAIL-CLOSED: iki yol ayrı büyüklük olursa künye YALAN olurdu."""
        from hrma.stability import hybrid_lfi as LFI
        r = LFI.assess_hybrid_lfi(**self.NOKTALAR[0])
        f, tau = r['frequency_hz'], r['boundary_layer_delay_s']
        # %1'lik bir kopma (ör. kırpma ya da ikinci bir model) yakalanmalı
        with pytest.raises(ValueError) as e:
            LFI.frekans_yollari_ozdeslik_kapisi(f * 1.01, tau)
        assert 'printing residual' in str(e.value).lower() or \
            'PRINTING RESIDUAL' in str(e.value)
        assert 'no number is published' in str(e.value)
        # Bandın hemen dışı da yakalanmalı (tolerans yastıklı değil)
        with pytest.raises(ValueError):
            LFI.frekans_yollari_ozdeslik_kapisi(
                f * (1.0 + 10.0 * LFI.LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL),
                tau)


class TestOHZ502ImDaraligi:
    """İm dar ve eşik ÖLÇÜLEN sayı; ikisi de sessizce büyüyemez."""

    def test_im_TEK_YAPRAK_yolu_ve_listede(self):
        from tests.test_field_wiring_layer_b import LEGITIMATE_CONSTANTS
        im = 'combustion_stability.lfi.frequency_paths_rel_diff'
        assert im in LEGITIMATE_CONSTANTS, 'OH-Z5-02 imi listede değil'
        # Blok-genel im (ör. yalnız 'lfi' ya da 'combustion_stability')
        # bloğa SONRADAN eklenecek uydurmayı da örterdi.
        assert im.count('.') >= 2 and im.endswith('rel_diff')
        for genis in ('combustion_stability', 'lfi', 'combustion_stability.lfi'):
            assert genis not in LEGITIMATE_CONSTANTS, (
                f'blok-genel im eklenmiş: {genis!r}')

    def test_esik_YUKSELTILMEDI_ve_kalan_borc_ADIYLA_yaziliyor(self):
        """Eşik YÜKSELTİLEMEZ; dokuz yaprağın izi kaybolamaz.

        ÇEVRİLDİ — ÖH D29 / termo-uçuş aşama-1 (OH-D28-01). Eski hâl eşiği
        RAKAMLA çiviliyordu (``'assert len(suspicious) <= 1' in m``) ve
        gerekçesi "eşik borcun ÖDENECEĞİ yeri gösterir, ulaşılan yeri
        değil" idi — yazıldığı gün DOĞRUYDU. Borç D29'da ÖDENDİ: dokuz
        yaprağın hepsi yaprak-başına ölçülüp sınıflandırıldı, sabit yaprak
        dökümü BOŞALDI (``docs/scofield/raw/OH/D29/termo-ucus/a1/
        sonra_constants.txt``, 0 bayt) ve eşik ölçülen değere (0) İNDİ.
        Çivi o andan itibaren YANLIŞ TARAFI korumaya başladı: eşiği
        İNDİRMEK bile bu testi kırıyordu. Aynı kalıp D25'te de yaşanmıştı
        (``test_d23_bekci_cevirisi_a1::…::test_esik_gevsetilmedi``in
        çevrilme gerekçesi).

        Korunan şey rakam değil SÖZLEŞMEDİR ve iddia ZAYIFLAMADI, üç
        yönden GÜÇLENDİ:
          (a) eşik iki yanlı ve YASTIKSIZ kalmalı (üst == alt),
          (b) D28'in bıraktığı 1'in ÜSTÜNE çıkılamaz — yasak artık
              dizgiyle değil KIYASLA duruyor, yani indirmeye izin verir
              yükseltmeye vermez,
          (c) dokuz yaprağın hiçbiri SESSİZCE kaybolamaz: her biri ya
              borç listesinde ADIYLA durur ya da DAR bir imle
              sınıflandırılmıştır; blok-genel im yasak.
        """
        import re
        m = (KOK / 'tests' / 'test_field_wiring_layer_b.py').read_text(
            encoding='utf-8')
        ust = re.search(r'assert len\(suspicious\) <= (\d+)', m)
        alt = re.search(r'assert len\(suspicious\) >= (\d+)', m)
        assert ust and alt, (
            'iki yönlü eşiğin bir yanı kaldırılmış — im ekleyerek borç '
            'kapatma sessiz kalır')
        assert int(ust.group(1)) == int(alt.group(1)), (
            'eşik YASTIKLI (üst %s, alt %s): araya yastık koymak yeni '
            'uydurma sabiti yutar' % (ust.group(1), alt.group(1)))
        assert int(ust.group(1)) <= 1, (
            'sabit yaprak eşiği %s\'e YÜKSELTİLMİŞ (D28 tabanı 1) — borcu '
            'gizlemek yasak' % ust.group(1))
        from tests.test_field_wiring_layer_b import LEGITIMATE_CONSTANTS
        for genis in ('acoustic_modes', 'mode_pool', 'seed_bounds',
                      'acoustic_modes.mode_pool', 'stability_report.chug',
                      'acoustic_modes.stability_report'):
            assert genis not in LEGITIMATE_CONSTANTS, (
                'blok-genel im eklenmiş: %r — bloğa SONRADAN eklenecek '
                'uydurma sabiti de örter' % genis)
        # Dokuz yaprağın her biri ya borç olarak ADIYLA yazılı, ya da DAR
        # bir imle sınıflandırılmış olmalı; ikisi de yoksa yaprak sessizce
        # kaybolmuş demektir.
        for yaprak in (
                '.motor.acoustic_modes.mode_pool.radial_max_n',
                '.motor.acoustic_modes.mode_pool.requested_n_modes',
                '.motor.acoustic_modes.mode_pool.returned_n_modes',
                '.motor.acoustic_modes.mode_pool.seed_bounds.longitudinal_max_q',
                '.motor.acoustic_modes.mode_pool.seed_bounds.radial_max_n',
                '.motor.acoustic_modes.mode_pool.seed_bounds.tangential_max_m',
                '.motor.acoustic_modes.mode_pool.tangential_max_m',
                '.motor.acoustic_modes.stability_report.chug.design_band_max_ratio',
                '.motor.acoustic_modes.stability_report.chug.design_band_min_ratio'):
            assert yaprak in m, f'kalan borç yaprağı adsız: {yaprak}'
        assert 'TERMO-UÇUŞ' in m, 'kalan borcun SAHİBİ yazılmamış'

    def test_taban_olcumu_kanit_dizininde(self):
        d = KOK / 'docs/scofield/raw/OH/D28/fea-cfd/a1'
        once = (kanit_gerekli(d / 'once_constants.txt')).read_text(encoding='utf-8').split()
        sonra = (kanit_gerekli(d / 'sonra_constants.txt')).read_text(encoding='utf-8').split()
        assert len(once) == 10 and len(sonra) == 9, (once, sonra)
        assert '.motor.combustion_stability.lfi.frequency_paths_rel_diff' \
            in once
        assert '.motor.combustion_stability.lfi.frequency_paths_rel_diff' \
            not in sonra


# ======================================================================
# OH-D27-05 — inceltme sürücüsü YAYIMLANAN kipi de izler
# ======================================================================
class TestOHD2705SurucuYayimlananKipiIzler:
    """Yakınsama ölçütü artık İKİ kipin konjonksiyonu (SIKI, gevşek değil)."""

    #: D24/D27/D28 boyunca ölçülen üç sıvı vakası (thrust N, Pc bar, ε).
    VAKALAR = ((25000.0, 70.0, 12.0), (2000.0, 15.0, 5.0),
               (1000.0, 10.0, 4.0))

    def test_surucu_ek_kip_parametresini_KABUL_EDER(self):
        import inspect

        from hrma.fea.structural_axisym import solve_with_refinement
        p = inspect.signature(solve_with_refinement).parameters
        assert 'ek_kip' in p, (
            'sürücü ek kip almıyor — yayımlanan kipin yakınsaması yine '
            'DURDUKTAN SONRA ölçülüyor demektir')
        assert p['ek_kip'].default is None

    def test_kopru_KARSIT_kipi_surucuye_VERIYOR(self):
        """Köprü ek kipi inceltmeden ÖNCE belirleyip sürücüye geçirir."""
        kaynak = (KOK / 'hrma' / 'fea' / 'bridge.py').read_text(
            encoding='utf-8')
        assert 'ek_kip=_surucu_ek_kip' in kaynak
        # Karşıt kip inceltme ÇAĞRISINDAN ÖNCE hesaplanmalı.
        assert (kaynak.index('_surucu_ek_kip = (karsit_kip')
                < kaynak.index('ref = solve_with_refinement(')), (
            'karşıt kip inceltmeden SONRA belirleniyor — sürücü onu '
            'izleyemez')

    @pytest.mark.parametrize('thrust,pc,er', VAKALAR)
    def test_UC_SIVI_VAKASINDA_yayimlanan_kip_KENDI_meshinde_yakinsar(
            self, thrust, pc, er):
        """1 kN vakası taban ölçümünde %10,07 ile DÜŞÜYORDU; artık %0,16.

        Ölçüm: ``once_d2705.json`` → ``sonra_d2705.json``.
        """
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.app import app
        from hrma.fea.bridge import run_structural_from_motor
        app.config['TESTING'] = True
        c = app.test_client()
        sivi = _sessiz(c.post, '/calculate_liquid', json={
            'motor_name': 'OH-D27-05', 'thrust': thrust, 'burn_time': 30.0,
            'chamber_pressure': pc, 'mixture_ratio': 2.2,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': er}).get_json()
        p = _sessiz(run_structural_from_motor, sivi)
        h = p['meta']['hukum']
        etiket = f'{thrust / 1000.0:g} kN / {pc:g} bar / eps={er:g}'
        assert h['converged_yayimlanan_kip'] is True, (
            f'{etiket}: yayımlanan kip KENDİ mesh yakınsamasını '
            'kanıtlayamadı — sürücü onu izlemiyor olabilir')
        assert 'yayimlanan_kip_yakinsamadi' not in \
            h['geri_cekme_gerekceleri'], etiket
        kd = p['meta']['kisit_duyarliligi']
        yk = kd.get('yayimlanan_kip_yakinsamasi') or {}
        if kd.get('yayimlanan_kip') != kd.get('birincil_kip'):
            # Yayımlanan kip birincilden farklıysa sürücü onu İZLEMİŞ olmalı
            assert yk.get('surucu_izledi') is True, (
                f'{etiket}: yayımlanan kip başka ama sürücü izlememiş: {yk}')
            assert yk.get('surucu_ek_tur', 0) >= 1, (
                f'{etiket}: ek kip hiç ölçülmemiş')
            assert yk['rel_change'] < yk['tol']

    def test_ek_kip_BIRINCILLE_AYNIYSA_yok_sayilir(self):
        """Aynı kip iki kez izlenmez (boş yere iki kat çözüm YOK)."""
        pytest.importorskip('numpy')
        import numpy as np

        from hrma.fea.structural_axisym import Material, solve_with_refinement
        z = np.linspace(0.0, 0.20, 24)
        r = 0.05 + 0.0 * z
        kontur = np.column_stack([z, r])
        mal = Material(E=200e9, nu=0.3, yield_strength=250e6)
        ref = _sessiz(solve_with_refinement, kontur, 0.004, mal,
                      inner_pressure=2.0e6, axial_fix='z_min',
                      n_axial0=8, n_radial0=2, max_rounds=1,
                      ek_kip='z_min')
        assert all(k.get('ek_kip_rel_change') is None for k in ref.history), (
            'birincil kiple aynı ek kip yine de ölçülmüş'
        )


# ======================================================================
# OH-D27-06 — kanonik "hüküm kazanılan vaka" KAYDI
# ======================================================================
class TestOHD2706KanonikKayit:
    """Beşinci elle taşımayı önleyen kayıt ürün kodunda ve künyeli."""

    def test_kayit_var_ve_ZORUNLU_alanlari_tasiyor(self):
        from hrma.fea.bridge import HUKUM_KAZANILAN_KANONIK_VAKA as K
        for alan in ('uc', 'govde', 'olculen', 'arama_izgarasi',
                     'kayit_dalgasi', 'kanit', 'basis'):
            assert alan in K, f'kanonik kayıtta {alan} yok'
        o = K['olculen']
        assert o['verildi'] is True
        assert o['geri_cekme_gerekceleri'] == []
        assert o['converged_birincil_kip'] is True
        assert o['converged_yayimlanan_kip'] is True
        # Kabul ARDIŞIK tur onayına dayanmalı (OH-D15-02 kazanımı).
        assert o['onay_ardisik_tur_sayaci'] >= o['onay_ardisik_tur_gerekli']
        assert o['final_rel_change'] < 0.01

    def test_kanit_dosyasi_GERCEKTEN_var_ve_kaydi_dogruluyor(self):
        from hrma.fea.bridge import HUKUM_KAZANILAN_KANONIK_VAKA as K
        # Yol ürün verisinden gelir (dinamik): tarayıcı göremez, kapı elle.
        p = kanit_gerekli(KOK / K['kanit'])
        assert p.exists(), f'kanıt yolu yok: {K["kanit"]}'
        d = json.loads(p.read_text(encoding='utf-8'))
        assert d['kanonik']['verildi'] is True
        assert d['kanonik']['geri_cekme_gerekceleri'] == []
        # Izgaranın gerçekten TARANDIĞI ve kazananların ölçüldüğü kanıtta
        # duruyor (kayıt bir tahmin değil).
        assert len(d.get('kazanan_vakalar') or []) >= 1

    def test_kayit_URUN_CIKTISINA_sizmaz(self):
        """Kayıt bir künyedir; hiçbir yanıt gövdesine girmez."""
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.app import app
        from hrma.fea.bridge import (HUKUM_KAZANILAN_KANONIK_VAKA,
                                     run_structural_from_motor)
        app.config['TESTING'] = True
        c = app.test_client()
        sivi = _sessiz(c.post, '/calculate_liquid',
                       json=HUKUM_KAZANILAN_KANONIK_VAKA['govde']).get_json()
        p = _sessiz(run_structural_from_motor, sivi)
        ham = json.dumps(p, default=str)
        assert 'arama_izgarasi' not in ham
        assert 'kayit_dalgasi' not in ham
