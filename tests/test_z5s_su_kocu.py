"""ÖH Z5S / PK4 — su koçu ve besleme adaptörü DAVRANIŞ bekçileri.

Kapsanan defter kalemleri
-------------------------
* **P4B4-01 (KRİTİK)** — kolon ayrılması fail-closed kapısı, tablonun KENDİ
  sayıları override olarak verilince kapanıyordu; ayrıca buhar basıncı
  bilinmediğinde "üst sınır değildir" diye uyarılan bir tepeden SAFE
  sertifikası veriliyordu.
* **P4B4-02** — kapanma süresi önerisi kolon ayrılmasını görmüyordu: hüküm
  MARGINAL iken öneri "kısıt gerekmez" diyor, ürettiği süre de hüküm
  basıncını MAWP içine indirmiyordu.
* **P4B4-07 / P5B3-02** — adaptör, besleme haritasında olmayan itici için
  sessizce ``fluid='water'`` yayımlıyor; etiketin tablo yoğunluğu hattın
  yoğunluğunun yerine geçiyordu (LH2 hattında debi 14,096 kat).
* **P4B4-08** — TEK ``pipe_material`` argümanı İKİ sözlüğe (pürüzlülük
  tablosu ⟷ materials_db) gidiyordu; kesişim boş olduğu için su koçu
  çözücüsü her çağrıda ss_304'e düşüp hükmü zorla MARGINAL yapıyordu.

BEKÇİ İLKESİ: burada kesin ondalık ÇAPALANMAZ (eşzamanlı onarımlar değer
kaydırabilir). Kilitlenen şey DAVRANIŞ ve KÜNYEDİR: hükmün neye bağlı
olduğu, hangi adın hangi tablodan çözüldüğü, hangi beyanın hangi koşulda
üretildiği. Sayısal ilişkiler (oran, eşiğin yeri, monotonluk) testin
İÇİNDE kurulur.
"""

import inspect
import math

import pytest

from hrma.analysis.water_hammer import (
    WaterHammerAnalyzer,
    FLUID_PROPERTIES,
    COLUMN_SEPARATION_PEAK_FACTOR,
    DEFAULT_PIPE_MATERIAL,
    MAWP_YIELD_SAFETY_FACTOR,
)
from hrma.analysis.valve_feedline import (
    analyze_valve_feedline,
    water_hammer_inputs,
    PIPE_ROUGHNESS_M,
    PIPE_ROUGHNESS_DEFAULT_KEY,
)
from hrma.data.materials_db import get_material, list_materials
from hrma.data.propellant_database import PropellantDatabase

# Ortak hat: 100 m x 100 mm x 6 mm, steel_4130. Sayılar bu testin kendi
# kurgusudur; hiçbir ürün sabitini yankılamaz.
HAT = dict(line_length_m=100.0, line_id_mm=100.0, wall_thickness_mm=6.0,
           pipe_material='steel_4130')
ADAPTOR_HAT = dict(line_id_m=0.0254, wall_thickness_m=0.0015,
                   line_length_m=5.0)


def _kos(**kw):
    # ÖH D18 / termo-ucus a1 (P4B4-09): çalışma basıncının REFERANS
    # DÜZLEMİ artık beyanlıdır. Bu fikstürün çalışma noktalarının bir
    # kısmı (ör. su 10 bar / 2 m/s, n2o 55 bar) tam da 1 atm'lik yorum
    # penceresinin içinde: mutlak okuma kolon ayrılması görüyor, gösterge
    # okuma görmüyor ve tasarım tepesi %31 değişiyor. Düzlem beyan
    # edilmezse modül artık hüküm vermeyi REDDEDER (fail-closed).
    # Bekçilerin İDDİALARI değişmedi; vaka yalnız düzlemini söylüyor.
    # 'absolute' seçildi: bu dosyanın konusu KOLON AYRILMASI kapısıdır ve
    # o kapı buhar basıncıyla kıyaslanan MUTLAK basınca bakar — taban
    # koddaki ayrılma hükmü de zaten mutlak okumadan geliyordu.
    p = dict(HAT)
    p.update(dict(fluid='water', working_pressure_bar=10.0,
                  flow_velocity_m_s=2.0,
                  working_pressure_reference='absolute'))
    p.update(kw)
    return WaterHammerAnalyzer().analyze(**p)


# ===========================================================================
# P4B4-01 — kolon ayrılması kapısı çağrı biçimine duyarlı olamaz
# ===========================================================================
class TestKolonAyrilmasiKapisi:

    @pytest.mark.parametrize('fluid', sorted(FLUID_PROPERTIES))
    @pytest.mark.parametrize('hiz', [2.0, 20.0])
    def test_override_kapiyi_kapatamaz(self, fluid, hiz):
        """Aynı fizik iki çağrı biçiminde AYNI hükmü vermeli.

        Tablo yolunda K ve rho tablodan çözülür; override yolunda AYNI iki
        sayı argüman olarak verilir. Hüküm çağrı biçiminden değil fizikten
        gelmelidir.
        """
        kayit = FLUID_PROPERTIES[fluid]
        ortak = dict(fluid=fluid, flow_velocity_m_s=hiz, pipe_mawp_bar=500.0)
        tablo = _kos(**ortak)
        ovr = _kos(bulk_modulus_Pa=kayit['bulk_modulus_Pa'],
                   density_kg_m3=kayit['density_kg_m3'], **ortak)
        assert ovr['peak_pressure_bar'] == pytest.approx(
            tablo['peak_pressure_bar'], rel=1e-12)
        assert ovr['column_separation'] == tablo['column_separation']
        assert ovr['vapor_pressure_Pa'] == tablo['vapor_pressure_Pa']
        assert ovr['design_peak_pressure_bar'] == pytest.approx(
            tablo['design_peak_pressure_bar'], rel=1e-12)
        assert ovr['status'] == tablo['status']

    def test_tablo_kaydi_override_ile_ozel_akiskana_donusmez(self):
        """Kaydın KÖKENİ yapısal alandan okunur; ezilen alan adıyla yazılır."""
        su = FLUID_PROPERTIES['water']
        ovr = _kos(bulk_modulus_Pa=su['bulk_modulus_Pa'])
        assert ovr['fluid_properties']['record_source'] == 'fluid_table'
        assert ovr['fluid_properties']['overridden_fields'] == [
            'bulk_modulus_Pa']
        assert ovr['vapor_pressure_source'] == 'fluid_table'
        # Tabloda OLMAYAN akışkan gerçekten özel kayıttır ve buhar basıncı
        # UYDURULMAZ.
        ozel = _kos(fluid='mystery', bulk_modulus_Pa=1.5e9,
                    density_kg_m3=900.0)
        assert ozel['fluid_properties']['record_source'] == 'user_custom_fluid'
        assert ozel['vapor_pressure_Pa'] is None
        assert ozel['vapor_pressure_source'] == 'unavailable'

    def test_override_ezdigi_alani_gercekten_kullanir(self):
        """Ezme YANKI değil: verilen K dalga hızını gerçekten oynatır."""
        su = FLUID_PROPERTIES['water']
        taban = _kos()
        yumusak = _kos(bulk_modulus_Pa=su['bulk_modulus_Pa'] / 4.0)
        # a ~ sqrt(K) (rijit terim) -> daha düşük K daha düşük dalga hızı.
        assert yumusak['wave_speed_rigid_m_s'] == pytest.approx(
            taban['wave_speed_rigid_m_s'] / 2.0, rel=1e-12)
        assert yumusak['wave_speed_m_s'] < taban['wave_speed_m_s']
        # ...ama buhar basıncı hâlâ tablodan: kapı açık kalmadı.
        assert yumusak['vapor_pressure_Pa'] == pytest.approx(
            float(su['vapor_pressure_Pa']), rel=1e-12)
        assert yumusak['column_separation'] is not None

    def test_buhar_basinci_bilinmezken_SAFE_sertifikasi_yok(self):
        """Değerlendirilemeyen kapı SAFE hükmünü engeller (fail-closed)."""
        out = _kos(fluid='mystery', bulk_modulus_Pa=1.5e9,
                   density_kg_m3=900.0, pipe_mawp_bar=500.0)
        assert out['column_separation'] is None
        assert out['status'] != 'SAFE'
        # Düşüşün sebebi ADIYLA söylenir (gerekçesiz hüküm yok).
        assert any('column-separation check could NOT be performed' in w
                   for w in out['warnings'])
        # Düşüş yalnız SAFE'i vurur: zaten UNSAFE olan hüküm YUMUŞATILMAZ.
        sert = _kos(fluid='mystery', bulk_modulus_Pa=1.5e9,
                    density_kg_m3=900.0, flow_velocity_m_s=80.0,
                    pipe_mawp_bar=5.0)
        assert sert['peak_pressure_bar'] > sert['pipe'][
            'hoop_yield_pressure_bar']
        assert sert['status'] == 'UNSAFE'
        assert not any('downgraded to MARGINAL' in w
                       for w in sert['warnings'])

    def test_kapi_degerlendirilince_hukum_basincini_yukari_tasir(self):
        """Ayrılma öngörülürse hüküm basıncı Joukowsky tepesinin ÜSTÜNDE."""
        out = _kos(flow_velocity_m_s=20.0, pipe_mawp_bar=500.0)
        assert out['column_separation'] is True
        assert out['design_peak_pressure_bar'] == pytest.approx(
            out['working_pressure_bar']
            + COLUMN_SEPARATION_PEAK_FACTOR * out['applied_pressure_rise_bar'],
            rel=1e-12)
        assert out['design_peak_pressure_bar'] > out['peak_pressure_bar']


# ===========================================================================
# P4B4-02 — öneri, hükmün dayandığı basıncı görmek zorunda
# ===========================================================================
class TestKapanmaSuresiOnerisi:

    @staticmethod
    def _izin_Pa(out):
        """Önerilen süreden GERİ ÇÖZÜLEN izin: dP = 2*rho*L*dv/t.

        İzin künyesi yanıta EKLENMEZ (ters-yön sözleşmesi: paneli olmayan
        alan yeni borç doğurur), bu yüzden bekçi onu ürünün kendi
        yayımladığı alanlardan Michaud bağıntısıyla geri çözer.
        """
        t_ms = out['recommended_closure_time_ms']
        if t_ms is None:
            return None
        return (2.0 * out['fluid_properties']['density_kg_m3']
                * out['inputs']['line_length_m'] * out['delta_v_m_s']
                / (t_ms / 1e3))

    @staticmethod
    def _marj_Pa(out):
        return (out['pipe']['mawp_bar'] - out['working_pressure_bar']) * 1e5

    def test_oneri_hukumle_celisemez(self):
        """Hüküm MAWP'yi aşıyorsa "kısıt gerekmez" cevabı yasak."""
    # ÖH D31 · P4B4-07 / OH-D27-08 — VAKA YENİDEN AYARLANDI (İDDİA AYNI).
    # n2o kaydı D31'de kanona taşındı (yoğunluk 785,0 -> 745,0 kg/m³,
    # N2O_LIQUID_DENSITY_SAT_25C; buhar basıncı 293,15 K -> 298,15 K).
    # Joukowsky artışı dP = rho*a*dv = sqrt(K*rho)*dv olduğundan daha
    # düşük yoğunluk daha düşük tepe verir: ÖLÇÜLDÜ, hüküm basıncı
    # 70,33 bar -> 69,93 bar'a indi ve 70 bar MAWP artık AŞILMIYOR, yani
    # vaka kendi rejiminden (MARGINAL) çıkıp SAFE'e düştü. Bekçinin
    # İDDİASI değişmedi ('hüküm MAWP'yi aşıyorsa kısıt gerekmez denemez');
    # yalnız vakayı o rejimde tutmak için MAWP 70 -> 68 bar'a alındı
    # (peak 62,47 < 68 < design 69,93). Tolerans/eşik GEVŞETİLMEDİ.
        out = _kos(fluid='n2o', working_pressure_bar=55.0, pipe_mawp_bar=68.0)
        assert out['column_separation'] is True
        assert out['design_peak_pressure_bar'] > out['pipe']['mawp_bar']
        assert not (out['recommended_closure_time_ms'] is None
                    and 'no closure-time restriction'
                    in out['recommendation'].lower())
        # Kısıtın sebebi metinde adıyla geçmeli.
        assert 'column separation' in out['recommendation'].lower()

    def test_onerilen_sure_hukum_basincini_mawpye_indirir(self):
        """Öneri uygulanınca HÜKÜM basıncı MAWP içinde kalır (yeterli)."""
        for mawp in (15.0, 30.0, 45.0):
            out = _kos(pipe_mawp_bar=mawp)
            t_rec = out['recommended_closure_time_ms']
            if t_rec is None:
                assert out['design_peak_pressure_bar'] <= out['pipe'][
                    'mawp_bar'] * (1 + 1e-9), (
                    f'MAWP {mawp} bar: kısıt gerekmiyor dendi ama hüküm '
                    'basıncı MAWP dışında')
                continue
            out2 = _kos(pipe_mawp_bar=mawp, valve_closure_time_ms=t_rec)
            assert out2['design_peak_pressure_bar'] <= out2['pipe'][
                'mawp_bar'] * (1 + 1e-6), (
                f'MAWP {mawp} bar: önerilen {t_rec:.1f} ms uygulandı, hüküm '
                f"basıncı {out2['design_peak_pressure_bar']:.3f} bar")

    def test_izin_rejimin_fonksiyonudur(self):
        """İzin, ayrılma yoksa MAWP marjı; varsa marjın çarpana bölümü."""
        # Ayrılma YOK (izin marjın kendisi): aşağı salınım buhar basıncının
        # üstünde kalacak kadar küçük bir marj seçilir.
        gevsek = _kos(pipe_mawp_bar=15.0)
        assert 'column separation' not in gevsek['recommendation'].lower()
        assert self._izin_Pa(gevsek) == pytest.approx(self._marj_Pa(gevsek),
                                                      rel=1e-9)
        # Ayrılma VAR (izin marjın çarpana bölümü).
        siki = _kos(pipe_mawp_bar=30.0)
        assert 'column separation' in siki['recommendation'].lower()
        assert self._izin_Pa(siki) == pytest.approx(
            self._marj_Pa(siki) / COLUMN_SEPARATION_PEAK_FACTOR, rel=1e-9)
        # Buhar basıncı BİLİNMEZSE ayrılma dışlanamaz -> yine çarpanla.
        korsuz = _kos(fluid='mystery', bulk_modulus_Pa=1.5e9,
                      density_kg_m3=900.0, pipe_mawp_bar=30.0)
        assert self._izin_Pa(korsuz) == pytest.approx(
            self._marj_Pa(korsuz) / COLUMN_SEPARATION_PEAK_FACTOR, rel=1e-9)

    def test_izin_asla_marjdan_buyuk_olamaz(self):
        """Hiçbir rejimde izin, MAWP marjını aşamaz (üst sınır kilidi)."""
        bakilan = 0
        for fluid in sorted(FLUID_PROPERTIES):
            for mawp in (20.0, 60.0, 200.0):
                out = _kos(fluid=fluid, working_pressure_bar=10.0,
                           pipe_mawp_bar=mawp)
                izin = self._izin_Pa(out)
                if izin is None:
                    # Kısıt gerekmiyorsa hüküm basıncı zaten MAWP içinde.
                    assert out['design_peak_pressure_bar'] <= out['pipe'][
                        'mawp_bar'] * (1 + 1e-9)
                    continue
                bakilan += 1
                assert 0.0 < izin <= self._marj_Pa(out) * (1 + 1e-9)
        assert bakilan >= 4, 'kurgu bozuldu: hiç kısıtlı vaka üretilmedi'


# ===========================================================================
# P4B4-08 — iki malzeme künyesi, iki sözlük, iki argüman
# ===========================================================================
class TestBoruMalzemesiAyrimi:

    def test_iki_argumanin_varsayilani_kendi_sozlugunde_cozulur(self):
        imza = inspect.signature(analyze_valve_feedline).parameters
        assert imza['pipe_material'].default == PIPE_ROUGHNESS_DEFAULT_KEY
        assert PIPE_ROUGHNESS_DEFAULT_KEY in PIPE_ROUGHNESS_M
        yapisal = imza['pipe_structural_material'].default
        assert yapisal in set(list_materials())
        get_material(yapisal)          # KeyError atmamalı

    def test_adaptor_cozulebilir_malzeme_yayimlar(self):
        """Adaptörün ürettiği anahtar çözücüde varsayıma DÜŞMEZ."""
        out = analyze_valve_feedline(
            mass_flow_kg_s=2.0, density_kg_m3=1141.0, viscosity_Pa_s=2.0e-4,
            inlet_pressure_Pa=25.0e5, valve_pressure_drop_Pa=2.0e5,
            fluid='lox', vapor_pressure_Pa=101325.0,
            line_id_m=ADAPTOR_HAT['line_id_m'],
            line_length_m=ADAPTOR_HAT['line_length_m'],
            wall_thickness_m=ADAPTOR_HAT['wall_thickness_m'])
        kw = out['water_hammer']['analyzer_kwargs']
        res = WaterHammerAnalyzer().analyze(**kw)
        assert res['pipe']['material'] == kw['pipe_material']
        assert res['inputs']['pipe_material_use_instead'] is None
        assert not any('Unknown pipe material' in w for w in res['warnings'])
        assert not any('ASSUMED material' in w for w in res['warnings'])

    def test_puruzluluk_yapisal_malzemeden_bagimsiz(self):
        """Yapısal malzeme değişince sürtünme AYNI, dalga hızı DEĞİŞİR."""
        ortak = dict(mass_flow_kg_s=2.0, density_kg_m3=1141.0,
                     viscosity_Pa_s=2.0e-4, inlet_pressure_Pa=25.0e5,
                     valve_pressure_drop_Pa=2.0e5, fluid='lox',
                     vapor_pressure_Pa=101325.0,
                     line_id_m=ADAPTOR_HAT['line_id_m'],
                     line_length_m=ADAPTOR_HAT['line_length_m'],
                     wall_thickness_m=ADAPTOR_HAT['wall_thickness_m'])
        a = analyze_valve_feedline(pipe_structural_material='ss_304', **ortak)
        b = analyze_valve_feedline(pipe_structural_material='aluminum_6061',
                                   **ortak)
        # Sürtünme yalnız pürüzlülükten: hat bütçesi bit-aynı.
        assert a['line']['total']['dp_Pa'] == b['line']['total']['dp_Pa']
        assert a['line']['inputs']['roughness_m'] == b['line']['inputs'][
            'roughness_m']
        # Dalga hızı yalnız yapısal malzemeden: alüminyum daha esnek ->
        # daha düşük dalga hızı (Wylie & Streeter Eş. 1-10).
        ra = WaterHammerAnalyzer().analyze(**a['water_hammer'][
            'analyzer_kwargs'])
        rb = WaterHammerAnalyzer().analyze(**b['water_hammer'][
            'analyzer_kwargs'])
        assert float(get_material('aluminum_6061')['elastic_modulus']) < float(
            get_material('ss_304')['elastic_modulus'])
        assert rb['wave_speed_m_s'] < ra['wave_speed_m_s']
        assert ra['wave_speed_rigid_m_s'] == pytest.approx(
            rb['wave_speed_rigid_m_s'], rel=1e-12)

    def test_pururzluluk_anahtari_yapisal_tabloya_gitmez(self):
        """Pürüzlülük anahtarı yapısal argümana verilirse REDDEDİLİR.

        İki tablonun kesişimi boştur; ayrım gerçekse pürüzlülük adı
        materials_db'de çözülemez ve çözücü bunu fail-closed ile söyler.
        """
        out = analyze_valve_feedline(
            mass_flow_kg_s=2.0, density_kg_m3=1141.0, viscosity_Pa_s=2.0e-4,
            inlet_pressure_Pa=25.0e5, valve_pressure_drop_Pa=2.0e5,
            fluid='lox', vapor_pressure_Pa=101325.0,
            pipe_structural_material=PIPE_ROUGHNESS_DEFAULT_KEY,
            line_id_m=ADAPTOR_HAT['line_id_m'],
            line_length_m=ADAPTOR_HAT['line_length_m'],
            wall_thickness_m=ADAPTOR_HAT['wall_thickness_m'])
        res = WaterHammerAnalyzer().analyze(
            **out['water_hammer']['analyzer_kwargs'])
        assert res['inputs']['pipe_material_submitted'] == (
            PIPE_ROUGHNESS_DEFAULT_KEY)
        assert res['inputs']['pipe_material_used'] == DEFAULT_PIPE_MATERIAL
        assert any('Unknown pipe material' in w for w in res['warnings'])
        assert res['status'] != 'SAFE'

    def test_kunye_gonderileni_ve_kullanilani_ayri_yazar(self):
        bilinmeyen = _kos(pipe_material='unobtanium')
        k = bilinmeyen['inputs']
        # Kanonik alan da GÖNDERİLENİ taşır: gönderilen ad çıktıdan silinmez.
        assert k['pipe_material'] == 'unobtanium'
        assert k['pipe_material_submitted'] == 'unobtanium'
        assert k['pipe_material_used'] == DEFAULT_PIPE_MATERIAL
        assert k['pipe_material_use_instead'] == DEFAULT_PIPE_MATERIAL
        assert bilinmeyen['pipe']['material'] == k['pipe_material_used']
        cozulen = _kos(pipe_material=DEFAULT_PIPE_MATERIAL)
        assert cozulen['inputs']['pipe_material_use_instead'] is None


# ===========================================================================
# P4B4-07 / P5B3-02 — akışkan etiketi uydurulmaz, yoğunluğu temsil eder
# ===========================================================================
class TestAkiskanEtiketi:

    def test_etiketsiz_cagri_su_etiketi_uydurmaz(self):
        """fluid verilmezse su koçu bağlaması ÜRETİLMEZ, sebebi yazılır."""
        out = analyze_valve_feedline(
            mass_flow_kg_s=2.0, density_kg_m3=70.8, viscosity_Pa_s=1.2e-5,
            inlet_pressure_Pa=25.0e5, valve_pressure_drop_Pa=2.0e5,
            line_id_m=ADAPTOR_HAT['line_id_m'],
            line_length_m=ADAPTOR_HAT['line_length_m'],
            wall_thickness_m=ADAPTOR_HAT['wall_thickness_m'])
        assert out['water_hammer'] is None
        beyan = [v for v in out['validity']
                 if v['field'] == 'water_hammer_inputs']
        assert beyan and beyan[0]['status'] == 'not_evaluated'
        assert 'no default fluid label' in beyan[0]['message']
        # Hat bütçesi ve vana boyutlandırma ETKİLENMEZ (kapsam dar).
        assert out['line']['total']['dp_Pa'] > 0.0
        assert out['valve']['capacity']['cv_required'] > 0.0

    def test_water_hammer_inputs_etiketsiz_cagriyi_reddeder(self):
        with pytest.raises(ValueError, match='fluid is required'):
            water_hammer_inputs(fluid=None, mass_flow_kg_s=2.0,
                                density_kg_m3=70.8,
                                working_pressure_Pa=25.0e5, **ADAPTOR_HAT)

    def test_cozucu_hattin_yogunlugunu_kullanir(self):
        """Etiketin tablo yoğunluğu hattın yoğunluğunun yerine geçemez."""
        rho = float(PropellantDatabase()
                    .get_propellant_properties('lh2')['density'])
        mdot = 2.0
        wh_in = water_hammer_inputs(fluid='water', mass_flow_kg_s=mdot,
                                    density_kg_m3=rho,
                                    working_pressure_Pa=25.0e5,
                                    **ADAPTOR_HAT)
        res = WaterHammerAnalyzer().analyze(**wh_in['analyzer_kwargs'])
        assert res['fluid_properties']['density_kg_m3'] == pytest.approx(
            rho, rel=1e-12)
        assert res['mass_flow_kg_s'] == pytest.approx(mdot, rel=1e-9)
        # Hız, hattın kendi sürekliliğinden: v = mdot/(rho*A).
        alan = math.pi * ADAPTOR_HAT['line_id_m'] ** 2 / 4.0
        assert res['flow_velocity_m_s'] == pytest.approx(
            mdot / (rho * alan), rel=1e-9)

    def test_etiket_yogunlugu_temsil_etmiyorsa_beyan_edilir(self):
        rho = float(PropellantDatabase()
                    .get_propellant_properties('lh2')['density'])
        wh_in = water_hammer_inputs(fluid='water', mass_flow_kg_s=2.0,
                                    density_kg_m3=rho,
                                    working_pressure_Pa=25.0e5,
                                    **ADAPTOR_HAT)
        etiket = wh_in['fluid_label']
        assert etiket['represents_line_density'] is False
        assert etiket['label_status'] == 'density_mismatch'
        assert etiket['density_ratio'] == pytest.approx(
            rho / float(FLUID_PROPERTIES['water']['density_kg_m3']),
            rel=1e-12)
        assert any('does NOT represent this line' in n
                   for n in wh_in['notes'])

    @pytest.mark.parametrize('fluid', sorted(FLUID_PROPERTIES))
    def test_tutarli_etikette_beyan_susar(self, fluid):
        wh_in = water_hammer_inputs(
            fluid=fluid, mass_flow_kg_s=2.0,
            density_kg_m3=FLUID_PROPERTIES[fluid]['density_kg_m3'],
            working_pressure_Pa=25.0e5, **ADAPTOR_HAT)
        assert wh_in['fluid_label']['represents_line_density'] is True
        assert wh_in['fluid_label']['label_status'] == 'consistent'
        assert not any('does NOT represent this line' in n
                       for n in wh_in['notes'])


# ===========================================================================
# Motor ayağı — adaptör bloğu ürün akışında ne yayımlıyor
# ===========================================================================
class TestMotorAdaptorBlogu:

    @staticmethod
    def _motor(**kw):
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
        p = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                 fuel_type='rp1', oxidizer_type='lox',
                 cooling_type='regenerative', injector_type='impinging')
        ovr = kw.pop('overrides', None)
        p.update(kw)
        motor = LiquidRocketEngine(overrides=dict(ovr or {}), **p)
        return motor, motor.calculate_performance()

    # ÖH D31 · P4B4-07 / OH-D27-08 — VAKA DEĞİŞTİ, İDDİA AYNI.
    # Bu bekçi "haritada OLMAYAN itici uydurma 'water' etiketi almaz" der.
    # D31'e kadar örneği METAN'dı; metan artık haritada (kaynak künyeli
    # NIST kaydı girdi), dolayısıyla eski vaka bu iddiayı ARTIK ÖLÇMÜYOR.
    # ÖLÇÜLDÜ: motorun DESTEKLEDİĞİ itici çiftleri ethanol/lox, lh2/lox,
    # methane/lox, mmh/n2o4, rp1/lox, udmh/n2o4'tür. Katalog listesinde
    # haritasız kalan h2o2 ve n2o bu çiftlerin HİÇBİRİNDE geçmez (yani
    # sıvı motordan ulaşılamazlar; vaka onlarla kurulamıyor —
    # UnsupportedPropellantPairError / UnsupportedPropellantDensityError).
    # Ulaşılabilir olup haritasız kalan TEK itici ETHANOL'dür; vaka ona
    # taşındı. Kurgu korundu: aynı koşumda bir hat haritasız (ethanol),
    # biri haritalı (lox).
    def test_haritasiz_itici_su_etiketi_almaz(self):
        """Haritasız yakıt hattı 'water' etiketi ALMAZ; sebebi adıyla yazılır."""
        _, sonuc = self._motor(fuel_type='ethanol',
                               overrides={'feed_line_wall_thickness': 2.0})
        hat = sonuc['detailed_feed_system']['valve_feedline']['fuel_line']
        assert hat['water_hammer_fluid_key'] is None
        assert hat['water_hammer'] is None
        assert 'not produced' in hat['water_hammer_coupling_source']
        assert 'ethanol' in hat['water_hammer_coupling_source']
        # Oksitleyici hattı (lox) haritada VAR: aynı koşumda üretiliyor.
        ox = sonuc['detailed_feed_system']['valve_feedline']['oxidizer_line']
        assert ox['water_hammer_fluid_key'] == 'lox'
        assert ox['water_hammer'] is not None
        assert ox['water_hammer']['analyzer_kwargs']['fluid'] == 'lox'

    def test_iki_blok_ayni_malzeme_kunyesini_okur(self):
        """Su koçu bloğu ile vana/hat bağlaması TEK malzeme adı kullanır."""
        _, sonuc = self._motor(overrides={'feed_line_wall_thickness': 2.0})
        wh = sonuc['detailed_feed_system']['water_hammer']['oxidizer_line']
        vf = sonuc['detailed_feed_system']['valve_feedline']['oxidizer_line']
        assert vf['pipe_structural_material'] == wh['inputs'][
            'pipe_material_submitted']
        assert vf['pipe_structural_material'] in set(list_materials())
        assert vf['water_hammer']['analyzer_kwargs']['pipe_material'] == (
            vf['pipe_structural_material'])
        # Kullanıcı malzemeyi değiştirince İKİSİ birden değişir.
        _, secili = self._motor(overrides={'feed_line_wall_thickness': 2.0,
                                           'feed_line_material': 'ss_316'})
        wh2 = secili['detailed_feed_system']['water_hammer']['oxidizer_line']
        vf2 = secili['detailed_feed_system']['valve_feedline'][
            'oxidizer_line']
        assert wh2['pipe']['material'] == 'ss_316'
        assert vf2['pipe_structural_material'] == 'ss_316'
        assert 'user input' in vf2['pipe_structural_material_source']

    def test_hat_puruzlulugu_olcuyle_gider_malzeme_adiyla_degil(self):
        """Motor pürüzlülüğü el kitabı sabitiyle verir ve kökenini
        ``handbook_table`` olarak beyan eder (ÖH D24 / P5B3-10 ŞART).

        Eski iddia ``'measured' in roughness_source`` idi ve KUSURU
        KORUYORDU: modül sabiti ``FEED_LINE_ROUGHNESS_M`` bu boruda
        ÖLÇÜLMÜŞ bir değer değil, paslanmaz boru finişi için el
        kitabından okunan bir sayıdır. Ürün (ÖH D18/D22) künyeyi
        düzelttiği an bekçi kırmızıya döndü — yani bekçi yalanı
        kilitliyordu. İddia artık künyenin GERÇEĞİ söylediğini
        kilitler: köken adıyla beyan edilir, künye metni tek kaynak
        olan ``ROUGHNESS_PROVENANCE``den gelir ve 'measured' DEMEZ.
        """
        from hrma.analysis.valve_feedline import ROUGHNESS_PROVENANCE
        from hrma.engines.liquid_rocket_engine import FEED_LINE_ROUGHNESS_M

        _, sonuc = self._motor(overrides={'feed_line_wall_thickness': 2.0})
        vf = sonuc['detailed_feed_system']['valve_feedline']['oxidizer_line']
        assert vf['line']['inputs']['roughness_m'] == pytest.approx(
            FEED_LINE_ROUGHNESS_M, rel=1e-12)
        assert vf['line']['inputs']['roughness_provenance'] == 'handbook_table'
        roughness_source = vf['line']['inputs']['roughness_source']
        assert roughness_source == ROUGHNESS_PROVENANCE['handbook_table']
        assert 'measured' not in roughness_source.lower()


# ===========================================================================
# Eşik kilidi — hüküm, MAWP ve akma basıncının BASAMAK fonksiyonudur
# ===========================================================================
class TestHukumEsikleri:

    @pytest.mark.parametrize('kesir,beklenen', [
        (0.98, 'SAFE'),
        (1.02, 'MARGINAL'),
        (MAWP_YIELD_SAFETY_FACTOR * 1.02, 'UNSAFE'),
    ])
    def test_esik_hukum_basincinin_fonksiyonu(self, kesir, beklenen):
        """Hedef hüküm basıncından TERSİNE çözülen hız, eşiğin yerini sınar."""
        p_work_bar = 10.0
        taban = _kos(working_pressure_bar=p_work_bar)
        mawp_bar = taban['pipe']['mawp_bar']
        hedef_bar = mawp_bar * kesir
        # Ayrılma rejiminde hüküm basıncı p_work + F*dP.
        dp_bar = (hedef_bar - p_work_bar) / COLUMN_SEPARATION_PEAK_FACTOR
        rho = float(FLUID_PROPERTIES['water']['density_kg_m3'])
        v = dp_bar * 1e5 / (rho * taban['wave_speed_m_s'])
        out = _kos(working_pressure_bar=p_work_bar, flow_velocity_m_s=v)
        assert out['column_separation'] is True
        assert out['design_peak_pressure_bar'] == pytest.approx(hedef_bar,
                                                                rel=1e-9)
        assert out['status'] == beklenen
