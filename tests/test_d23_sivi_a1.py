# -*- coding: utf-8 -*-
"""ÖH Dalga-23 · sıvı kulvarı, aşama 1 — onarım bekçileri.

Kapsanan defter kalemleri:
  P17B1-10  ekrana basılan beyanın İÇİNDE karışık dil (ham Türkçe dize)
  P16B2-07  η_c* girdi/çıktı birim sözleşmesi (kesir ⟷ yüzde)
  OH-D18-08 ε kırpması uyarı kanalına düşmüyordu
  OH-D19-14 /calculate_liquid yanıtında openrocket bloğu yoktu
  P17B3-03  sıvı akustik bloğu lüle girişi ortalama akış Mach'ını vermiyordu
  P3B1-09   ölü öznitelik self.gamma_combustion
  P3B1-10   soğutma kanalı docstring'i 'oda çapı' diyordu, kod boğazı kullanıyor
  P3B1-13   önbellek dokümanı 'geometri optimumu değiştirmez' diyordu
  P3B2-13   ölü kod + uydurma yüzey gerilimi sabiti

Her bekçi ters-mutasyonla kırmızıya çevrildi; kanıt
docs/scofield/raw/OH/D23/sivi/a1/mutasyon.json.
"""
import io
import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MOTOR = KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
PANEL = KOK / 'hrma' / 'static' / 'js' / 'panels' / 'stability_panel.js'
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'

TR_HARF = re.compile(r'[çğıİöşüÇĞÖŞÜ]')

TABAN_YUK = {
    'motor_name': 'D23-SIVI', 'thrust': 10000.0, 'burn_time': 30.0,
    'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0,
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(client, **ek):
    yuk = dict(TABAN_YUK)
    yuk.update(ek)
    yanit = client.post('/calculate_liquid', json=yuk)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    return yanit.get_json()


@pytest.fixture(scope='module')
def taban(client):
    return _kos(client)


def _uyari_kodlari(govde):
    return [u.get('code') for u in (govde.get('input_warnings') or [])
            if isinstance(u, dict)]


def _uyari(govde, kod):
    for u in (govde.get('input_warnings') or []):
        if isinstance(u, dict) and u.get('code') == kod:
            return u
    return None


# ---------------------------------------------------------------------------
# P17B1-10 — sıvı motorun EKRANA basılan beyanı tek dilde olmalı
# ---------------------------------------------------------------------------
class TestP17B1_10KarisikDil:
    """Ölçülen kusur: 'Autogenous pressurization: Autogenous basınçlandırma
    turbopompalı çevrimler içindir…' — İngilizce başlık, Türkçe gövde.

    Ürün sözleşmesi (app.py: 'i18n: backend EN üretir; TR karşılığı
    sözlükte'): çözücünün ürettiği beyan metni İNGİLİZCEDİR. Bu bekçi
    liquid_rocket_engine.py'nin SAHİBİ olduğu beyan yapraklarını tutar.
    """

    #: (yol, açıklama) — hepsi liquid_rocket_engine.py'de üretilir.
    YAPRAKLAR = (
        ('feed_system.pressurization.type_basis', '_pressurization_type'),
        ('autogenous_pressurization.reason', '_autogenous_applicable'),
        ('combustion_analysis.stability_analysis.acoustic_analysis_note',
         '_stability_assessment'),
        ('combustion_analysis.stability_analysis.chug_basis',
         '_stability_assessment'),
    )

    @staticmethod
    def _pick(govde, yol):
        cur = govde
        for a in yol.split('.'):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(a)
        return cur

    @pytest.mark.parametrize('yol,kaynak', YAPRAKLAR)
    def test_beyan_yapragi_turkce_harf_tasimaz(self, taban, yol, kaynak):
        metin = self._pick(taban, yol)
        if metin is None:
            pytest.skip('%s bu koşuda yayımlanmadı' % yol)
        assert isinstance(metin, str)
        assert not TR_HARF.search(metin), (
            '%s (%s) hâlâ Türkçe harf taşıyor: %r' % (yol, kaynak, metin[:180]))

    def test_kisma_haritasi_kabulleri_turkce_harf_tasimaz(self, taban):
        kabuller = (taban.get('throttle_map') or {}).get('assumptions') or []
        assert kabuller, 'throttle_map.assumptions boş'
        kirli = [k for k in kabuller if TR_HARF.search(str(k))]
        assert not kirli, 'Türkçe kalan kabul satırları: %r' % kirli[:3]

    def test_autogenous_notu_turkce_harf_tasimaz(self, client):
        govde = _kos(client, fuel_type='methane',
                     feed_system_type='turbopump')
        blok = govde.get('autogenous_pressurization') or {}
        not_metni = blok.get('note')
        if not_metni is None:
            pytest.skip('bu koşuda autogenous boyutlandırma üretilmedi')
        assert not TR_HARF.search(not_metni), not_metni[:180]

    def test_basinc_beslemeli_autogenous_reddi_tek_dilde(self, client):
        """Ölçülen kusurun TAM cümlesi buradan geliyordu: besleme kolu
        (``engine_cycle='pressure_fed'``) reddi. Ekranda "Autogenous
        pressurization: Autogenous basınçlandırma turbopompalı çevrimler
        içindir…" diye çıkıyordu."""
        govde = _kos(client, fuel_type='methane', mixture_ratio=2.8,
                     engine_cycle='pressure_fed')
        gerekce = (govde.get('autogenous_pressurization') or {}).get('reason')
        assert isinstance(gerekce, str) and gerekce, (
            'basınç beslemeli koşuda autogenous reddi yayımlanmadı')
        assert 'turbopump' in gerekce
        assert not TR_HARF.search(gerekce), gerekce[:200]

    def test_reddedilen_autogenous_kunyesi_tek_dilde(self, client):
        govde = _kos(client, feed_system_type='pressure_fed',
                     pressurization_type='autogenous')
        kunye = ((govde.get('feed_system') or {}).get('pressurization')
                 or {}).get('type_basis')
        assert isinstance(kunye, str) and kunye
        assert 'rejected' in kunye
        assert not TR_HARF.search(kunye), kunye[:200]


# ---------------------------------------------------------------------------
# P16B2-07 — η_c* birim sözleşmesi
# ---------------------------------------------------------------------------
class TestP16B2_07BirimSozlesmesi:
    """Yanıt η_c*'ı KESİR yayımlıyor, girdi alanı YÜZDE okunuyor.

    Ölçüldü (once.json): alan uca BAĞLI (97 -> 0,97 'user input'), yani
    kalemin 'kullanıcının 0,97'sine 1,0 uygulanıp user input yazılıyor'
    başlığı bu ağaçta çürük. Kalan kusur birim asimetrisiydi: yanıttan
    okunan 0,97'yi geri gönderen çağıran sessizce ideal η_c* alıyordu ve
    girdinin biriminin yüzde olduğu yanıtın HİÇBİR yerinde yazmıyordu.
    """

    @staticmethod
    def _inj(govde):
        return govde.get('injection_system') or govde.get('injector_design') or {}

    def test_yuzde_girdi_uygulanir_ve_kunyesi_dogru(self, client):
        govde = _kos(client, combustion_efficiency=97)
        inj = self._inj(govde)
        assert inj['combustion_efficiency'] == pytest.approx(0.97, abs=1e-9)
        assert inj['combustion_efficiency_source'] == (
            'user input (combustion efficiency)')

    def test_kesir_girdi_reddedilir_ve_birim_adiyla_soylenir(self, client):
        govde = _kos(client, combustion_efficiency=0.97)
        inj = self._inj(govde)
        # Sessiz dönüşüm YOK: değer uygulanmaz.
        assert inj['combustion_efficiency'] == pytest.approx(1.0, abs=1e-9)
        assert inj['combustion_efficiency_source'].startswith('not supplied')
        # Ret GEREKÇESİ adıyla söylenir.
        u = _uyari(govde, 'warn.liquid.efficiency_unit_is_percent')
        assert u is not None, _uyari_kodlari(govde)
        p = u['params']
        assert p['field'] == 'combustion_efficiency'
        assert p['value'] == pytest.approx(0.97)
        assert p['as_percent'] == pytest.approx(97.0)

    def test_birim_sozlesmesi_yanitta_yazili(self, taban):
        inj = self._inj(taban)
        assert inj['combustion_efficiency_unit'] == 'fraction'
        assert inj['combustion_efficiency_input_unit'] == 'percent'
        assert inj['combustion_efficiency_input_band'] == [50.0, 100.0]
        assert 'FRACTION' in inj['combustion_efficiency_unit_contract']
        assert 'PERCENT' in inj['combustion_efficiency_unit_contract']

    def test_band_tek_tanim_yerinden_okunur(self):
        kaynak = MOTOR.read_text(encoding='utf-8')
        assert 'COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT = (50.0, 100.0)' in kaynak
        # Bandın satır-içi kopyası kalmamalı.
        assert "'combustion_efficiency', 50.0, 100.0" not in kaynak
        assert kaynak.count('COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT') >= 4


# ---------------------------------------------------------------------------
# OH-D18-08 — ε kırpması uyarı kanalına düşer
# ---------------------------------------------------------------------------
class TestOHD1808KirpmaUyarisi:
    """Kırpma OLGUSU yalnız nozzle_angles.expansion_ratio_clamp alanındaydı;
    ekranın uyarı kanalına hiç düşmüyordu."""

    def test_kirpilan_kosu_uyari_uretir(self, client):
        # Pc = 10 bar: ortam-eşlenik ε 2,35 -> taban 2,5'e kırpılır.
        govde = _kos(client, chamber_pressure=10.0)
        na = govde.get('nozzle_angles') or {}
        assert na.get('expansion_ratio_clamp') == 'floor', na.get(
            'expansion_ratio_clamp')
        u = _uyari(govde, 'warn.liquid.expansion_ratio_clamped')
        assert u is not None, _uyari_kodlari(govde)
        p = u['params']
        assert p['edge'] == 'floor'
        assert p['eps_clamped'] == pytest.approx(2.5, abs=1e-6)
        assert p['eps_unclamped'] < p['eps_clamped']
        assert p['lo'] == pytest.approx(2.5)

    def test_kirpilmayan_kosu_uyari_uretmez(self, taban):
        assert (taban.get('nozzle_angles') or {}).get(
            'expansion_ratio_clamp') is None
        assert 'warn.liquid.expansion_ratio_clamped' not in _uyari_kodlari(taban)

    def test_kod_iki_dilde_sozlukte(self):
        js = SOZLUK.read_text(encoding='utf-8')
        assert js.count("'warn.liquid.expansion_ratio_clamped'") == 2
        assert js.count("'warn.liquid.efficiency_unit_is_percent'") == 2


# ---------------------------------------------------------------------------
# OH-D19-14 — openrocket bloğu sıvı yanıtında
# ---------------------------------------------------------------------------
class TestOHD1914OpenRocketBlogu:
    def test_blok_var_ve_hibritle_ayni_semayi_tasir(self, taban):
        blok = taban.get('openrocket')
        assert isinstance(blok, dict), 'sıvı yanıtında openrocket bloğu yok'
        for alan in ('eng_file', 'eng_error', 'eng_envelope_warning',
                     'motor_summary', 'flight_profile'):
            assert alan in blok, alan

    def test_sahte_eng_yazilmaz_ret_adiyla_beyan_edilir(self, taban):
        blok = taban['openrocket']
        hata = blok.get('eng_error')
        if hata is None:
            assert blok.get('eng_file'), (
                'ne .eng dosyası ne de ret gerekçesi var')
            return
        assert hata['error'] == 'missing_export_data'
        assert hata['missing_fields'], 'eksik alanlar ADIYLA sayılmalı'
        assert blok.get('eng_file') is None, 'ret varken .eng yazılmamalı'

    def test_ucus_profili_uydurulmaz(self, taban):
        blok = taban['openrocket']
        assert blok['flight_profile'] is None
        assert 'no vehicle is assumed' in blok['flight_profile_reason']


# ---------------------------------------------------------------------------
# P17B3-03 — sıvı akustik bloğu M_N'i çözer
# ---------------------------------------------------------------------------
class TestP17B3_03LuleGirisiMach:
    @staticmethod
    def _modlar(govde):
        return (((govde.get('combustion_analysis') or {})
                 .get('stability_analysis') or {})
                .get('acoustic_modes') or {})

    def test_mach_cozulur_ve_fizikseldir(self, taban):
        blok = self._modlar(taban)
        assert blok.get('status') == 'modelled', blok.get('status')
        m_n = blok.get('mean_flow_mach_M_N')
        assert isinstance(m_n, float), m_n
        assert 0.0 < m_n < 1.0, m_n

    def test_ozdeslik_yanitin_kendi_buyuklukleriyle_kurulur(self, taban):
        blok = self._modlar(taban)
        rho = blok['chamber_gas_density_kg_m3']
        a = blok['sound_speed_m_s']
        s_c = blok['acoustic_cavity_area_m2']
        mdot = blok['mass_flow_kg_s']
        assert blok['mean_flow_mach_M_N'] == pytest.approx(
            mdot / (rho * a * s_c), rel=1e-9)
        assert mdot == pytest.approx(taban['total_mass_flow'], rel=1e-6)

    def test_panel_sivi_kaynagini_okur(self):
        js = PANEL.read_text(encoding='utf-8')
        assert ("'combustion_analysis.stability_analysis.acoustic_modes'\n"
                "                    + '.mean_flow_mach_M_N'") in js


# ---------------------------------------------------------------------------
# P3B1-09 / P3B1-10 / P3B1-13 / P3B2-13 — ölü kod ve bayat beyan
# ---------------------------------------------------------------------------
class TestOluKodVeBayatBeyan:
    @pytest.fixture(scope='class')
    def kaynak(self):
        """Motor kaynağı — YORUM satırları çıkarılmış.

        Onarım gerekçeleri silinen literalleri yorumda ANIYOR (defter
        izlenebilirliği); bekçi yalnız ÇALIŞAN kodu taramalı.
        """
        ham = MOTOR.read_text(encoding='utf-8').splitlines()
        return '\n'.join(l for l in ham if not l.lstrip().startswith('#'))

    def test_p3b1_09_olu_oznitelik_yok(self, kaynak):
        assert 'self.gamma_combustion' not in kaynak

    def test_p3b1_09_motorda_oznitelik_yok(self):
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
        motor = LiquidRocketEngine(
            thrust=10000.0, chamber_pressure=30.0, mixture_ratio=2.2,
            fuel_type='rp1', oxidizer_type='lox')
        assert not hasattr(motor, 'gamma_combustion')

    def test_p3b1_10_docstring_bogazi_soyler(self, kaynak):
        i = kaynak.index('def _cooling_channel_geometry')
        govde = kaynak[i:i + 1600]
        # ÖH A2 sivi-sogutma F-17 (Berke Sunum 2 onayı sonrası çeviri,
        # denetçi Ş5.8): docstring GÜNCEL ölçütü söyler (kanal tabanı çevresi,
        # boğazda); 'D_hazne' yasağı aynen.
        assert '2·pi·(r_boğaz + t_sıcak_cidar)' in govde
        assert 'n = floor(pi·D_hazne' not in govde
        # Kod da boğazı kullanıyor olmalı (beyan ⟷ kod bağı).
        assert "d_ref = getattr(self, 'd_t', None)" in govde

    def test_p3b1_13_onbellek_beyani_geometriyi_yok_saymaz(self, kaynak):
        i = kaynak.index('def _optimal_mr_scan_cached')
        govde = kaynak[i:i + 2600]
        assert ('Optimum yalnız (itici çifti, Pc, referans eps) '
                'fonksiyonudur') not in govde
        assert 'lüle geometrisi optimumu DEĞİŞTİRİR' in govde

    def test_p3b2_13_olu_sabitler_gitti(self, kaynak):
        for olu in ('ablative_thickness = 0.01',
                    'ablative_recession_rate = 0.1e-3',
                    'injection_angle = 60',
                    'v_fuel_base = 18  # m/s (verified)',
                    'v_ox_base = 40'):
            assert olu not in kaynak, olu

    def test_p3b2_13_yuzey_gerilimi_tek_kaynaktan(self, kaynak):
        assert 'surface_tension = 0.02' not in kaynak
        assert 'liquid_surface_tension(self.fuel_type)' in kaynak
        assert 'liquid_surface_tension(self.oxidizer_type)' in kaynak

    def test_p3b2_13_sigma_tablodan_gelir_ve_kunyeli(self, taban):
        """Ölçülen: LOX'un tablo değeri 0,013145 N/m; eski çıplak sabit
        0,02 idi ve 'typical for cryogenics' diyerek RP-1'e de uygulanıyordu.
        Yakıt tarafında (RP-1) modülün tablosunda kayıt YOK - o hâlde sayı
        uydurulmaz, 'generic' KÜNYESİYLE bildirilir."""
        blok = taban['injection_system']
        assert blok['atomisation_surface_tension_ox_N_m'] == pytest.approx(
            0.013145, rel=1e-9), 'oksitleyici sigma tablo değeri değil'
        assert blok['atomisation_surface_tension_ox_source'] == 'table'
        assert blok['atomisation_surface_tension_fuel_source'] == 'generic'
        assert blok['droplet_diameter_governing_circuit'] in (
            'fuel', 'oxidizer')
        assert blok['fuel_droplet_diameter'] > 0
        assert blok['ox_droplet_diameter'] > 0
        # NOT: skaler ``droplet_diameter`` injector_design modülü çözünce
        # onun SMD korelasyonuyla EZİLİR (modülün kendi künyesi bunu söyler),
        # bu yüzden burada iki devre değeriyle eşitlik ARANMAZ. Aranan:
        # yedek tahminin hangi devreden geldiğinin ADIYLA yazılı olması.
        assert 'COARSER of the two circuits' in blok[
            'atomisation_surface_tension_basis']

    def test_p3b2_13_sigma_akiskana_gore_degisir(self, client):
        """Eski çıplak sabit HER akışkana aynı 0,02'yi veriyordu."""
        n2o4 = _kos(client, fuel_type='mmh', oxidizer_type='n2o4',
                    mixture_ratio=2.1)
        lox = _kos(client)
        a = n2o4['injection_system']
        b = lox['injection_system']
        assert a['atomisation_surface_tension_ox_N_m'] != pytest.approx(
            b['atomisation_surface_tension_ox_N_m']), (
            'oksitleyici değişti, sigma değişmedi -> yine akışkandan '
            'bağımsız sabit')
        assert a['atomisation_surface_tension_ox_source'] == 'generic'
        assert b['atomisation_surface_tension_ox_source'] == 'table'
