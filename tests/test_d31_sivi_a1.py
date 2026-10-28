"""ÖH Dalga-31 · SIVI kulvarı aşama-1 bekçileri.

Kapsanan kalemler
-----------------
P4B4-07 + OH-D27-08 (ÇİFT)  su koçu akışkan haritası: veri borcunun ödenen
                            kısmı + n2o kanon ayrışmasının kapanması
OH-D25-25                   dump_cooling ΔP / ceket debisi not_modelled +
                            WALL_TEMP_DEFAULT_K künyesi
OH-D30-05                   akustik göç manifestosunun "bugün yeniden
                            üretilebilir" iddiasının kapsamı
OH-FT-04                    kanıt dosyası hijyeni (JSON gerçekten JSON)
OH-FT-05                    P3B4-11 künyesinin STATİK TABLO yolundaki kilidi
OH-D21-09                   Rao λ araması: kayıtlı arama + statüko kilidi
B4-10                       power_residual_rel'in dürüst künyesi

Her bekçi ters-mutasyonla kırmızı görüldü; kanıt
``docs/scofield/raw/OH/D31/sivi/a1/mutasyon.json``.
"""

import contextlib
import io
import json
import math
import os
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from hrma.analysis import water_hammer as WH                    # noqa: E402
from hrma.data import propellant_database as PDB                # noqa: E402
from hrma.engines import liquid_rocket_engine as LRE            # noqa: E402


def oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


# ===========================================================================
# P4B4-07 + OH-D27-08 — su koçu akışkan haritası
# ===========================================================================
#: D31'de haritaya giren iticiler ve birincil kaynaklarının ses hızı [m/s].
#: Ses hızı BİRİNCİL VERİDİR; K burada değil üründe türetilir, bekçi yalnız
#: kimliği ölçer.
D31_YENI_HARITA = {
    'lh2': (1129.1, PDB.LH2_LIQUID_DENSITY_20K),
    'methane': (1338.1, PDB.METHANE_LIQUID_DENSITY_NBP),
    'mmh': (1548.0, PDB.MMH_LIQUID_DENSITY_293K),
    'udmh': (1247.0, PDB.UDMH_LIQUID_DENSITY_293K),
    'n2o4': (997.0, PDB.N2O4_LIQUID_DENSITY_293K),
}


class TestP4B407SuKocuHaritasi:

    def test_bes_itici_haritaya_girdi(self):
        """Ödenen borç geri alınamaz: beş itici haritada OLMAK ZORUNDA."""
        for itici in D31_YENI_HARITA:
            assert LRE.WATER_HAMMER_FLUID_KEY.get(itici) == itici, (
                f'{itici} su koçu haritasından düşmüş (P4B4-07 borcu '
                'geri alınamaz)')
        # lox/rp1 de yerinde: genişleme eskiyi ezmedi.
        assert LRE.WATER_HAMMER_FLUID_KEY['lox'] == 'lox'
        assert LRE.WATER_HAMMER_FLUID_KEY['rp1'] == 'rp1'

    def test_K_gercekten_rho_a_karesinden_TURETILIYOR(self):
        """K = rho*a^2 kimliği BİT düzeyinde durmalı (sayı transkribe edilmez).

        Kaydın ``bulk_modulus_Pa`` alanı elle yazılmış bir sayı olsaydı
        yoğunluk ya da ses hızı değiştiğinde sessizce ayrışırdı — n2o'nun
        785 ⟷ 745 hastalığının aynısı. Bu bekçi ayrışmayı imkânsız kılar.
        """
        for itici, (a_src, _rho) in D31_YENI_HARITA.items():
            rec = WH.FLUID_PROPERTIES[itici]
            assert rec['sound_speed_m_s'] == a_src, (
                f'{itici}: kaydın ses hızı birincil kaynaktan sapmış')
            beklenen = WH.bulk_modulus_from_sound_speed(
                rec['density_kg_m3'], rec['sound_speed_m_s'])
            assert rec['bulk_modulus_Pa'] == beklenen, (
                f'{itici}: K artık rho*a^2 değil — sayı elle yazılmış')
            # Ters yön: tablodaki K'dan geri çözülen ses hızı kaynağın
            # kendisini vermeli (boyut kimliği de böylece kapanır).
            a_geri = math.sqrt(rec['bulk_modulus_Pa'] / rec['density_kg_m3'])
            assert a_geri == pytest.approx(a_src, rel=1e-12)

    def test_yogunluk_MERKEZI_katalogdan_okunuyor(self):
        """Su koçu kaydı ikinci bir yoğunluk sayısı YAZAMAZ (tek kaynak)."""
        db = PDB.PropellantDatabase()
        for itici in sorted(set(LRE.WATER_HAMMER_FLUID_KEY)):
            rec = WH.FLUID_PROPERTIES[LRE.WATER_HAMMER_FLUID_KEY[itici]]
            merkez = float(db.get_propellant_properties(itici)['density'])
            assert float(rec['density_kg_m3']) == pytest.approx(
                merkez, rel=1e-12), (
                f'{itici}: su koçu {rec["density_kg_m3"]} kg/m³, merkezî '
                f'katalog {merkez} kg/m³ — iki yerde iki sayı')

    def test_n2o_kanon_ayrismasi_KAPANDI(self):
        """n2o kaydı artık merkezî kanon adını okur; sayı ikinci kez yazılmaz."""
        rec = WH.FLUID_PROPERTIES['n2o']
        assert rec['density_kg_m3'] == PDB.N2O_LIQUID_DENSITY_SAT_25C, (
            'n2o su koçu yoğunluğu merkezî kanondan ayrışmış (ölçülen eski '
            'ayrışma 785,0 - 745,0 = 40 kg/m³)')
        # Yoğunluk ile buhar basıncı AYNI anma durumunu anlatmalı.
        assert rec['vapor_pressure_ref_K'] == pytest.approx(298.15), (
            'n2o kaydı iki farklı sıcaklığın sayılarını taşıyor: yoğunluk '
            '298,15 K kanonundan, buhar basıncı başka bir sıcaklıktan'
        )

    def test_h2o2_FAIL_CLOSED_kalir(self):
        """Kaynağı olmayan alan uydurulmaz; kayıt haritaya da girmez."""
        rec = WH.FLUID_PROPERTIES['h2o2']
        assert rec.get('vapor_pressure_Pa') is None, (
            'h2o2 buhar basıncı için birincil kaynak KAZANILMADI — sayı '
            'girilmiş olamaz'
        )
        assert 'h2o2' not in LRE.WATER_HAMMER_FLUID_KEY, (
            'buhar basıncı olmayan kayıt haritaya giremez: harita aynı '
            'zamanda NPSH/kavitasyon buhar basıncı kaynağıdır'
        )
        # Ama K/rho künyeli olarak DURUYOR (özel çağrı kullanabilsin).
        assert rec['bulk_modulus_Pa'] > 0 and rec['source']

    def test_torr_cevrimi_TANIMDAN_gelir(self):
        """1 Torr = 1 atm / 760 — ikinci bir sayı yazılmaz."""
        from hrma.constants import P_SEA_LEVEL_PA
        assert WH.TORR_PA == P_SEA_LEVEL_PA / 760.0
        assert WH.FLUID_PROPERTIES['mmh']['vapor_pressure_Pa'] == (
            49.47 * WH.TORR_PA)
        assert WH.FLUID_PROPERTIES['udmh']['vapor_pressure_Pa'] == (
            167.1 * WH.TORR_PA)
        assert WH.FLUID_PROPERTIES['n2o4']['vapor_pressure_Pa'] == (
            898.57 * WH.TORR_PA)

    def test_capraz_denetim_bandi_IKI_belirlemeyi_kapsar(self):
        """mmh/udmh/n2o4: K = 1/beta_s belirlemesi bandın İÇİNDE olmalı."""
        for itici, beta_s in (('mmh', 4.88e-05), ('udmh', 8.23e-05),
                              ('n2o4', 7.44e-05)):
            rec = WH.FLUID_PROPERTIES[itici]
            k_alt = WH.bulk_modulus_from_compressibility(beta_s)
            alt, ust = rec['bulk_modulus_band_Pa']
            assert alt <= k_alt <= ust, (
                f'{itici}: bağımsız çapraz denetim K = 1/beta_s = '
                f'{k_alt / 1e6:.1f} MPa bandın dışında')
            assert alt <= rec['bulk_modulus_Pa'] <= ust

    def test_urun_bes_itici_icin_su_kocu_blogu_URETIYOR(self):
        """Kapsama ölçümü ürün ucunda: haritalı hatta blok gerçekten doğar."""
        hat = dict(line_length_m=2.0, line_id_mm=25.0, wall_thickness_mm=2.0,
                   working_pressure_bar=25.0, flow_velocity_m_s=6.0,
                   valve_closure_time_ms=20.0, pipe_material='ss_304')
        for itici in D31_YENI_HARITA:
            with contextlib.redirect_stdout(io.StringIO()):
                r = WH.WaterHammerAnalyzer().analyze(fluid=itici, **hat)
            assert r['wave_speed_m_s'] > 0
            assert r['joukowsky_pressure_rise_bar'] > 0


# ===========================================================================
# OH-D25-25 — dump soğutma ceket ayağı + WALL_TEMP_DEFAULT_K künyesi
#
# ÖLÇÜLDÜ (once_dump.json, tabanda, 25 kN RP-1/LOX):
#   dump_cooling ve regenerative blokları ceket debisinde ve ΔP'de BİT-AYNI
#   (2,561458273760645 kg/s ⟷ 3,761542589148719 bar) ve dump bloğunun künyesi
#   kelimesi kelimesine "regenerative jacket flow ..." diyordu. Dump soğutmada
#   soğutucu hazneye DÖNMEZ, dışarı atılır; debisi yakıt bütçesinin tamamı
#   değil kaynak künyeli bir BLEED KESRİDİR. O kesrin modeli kazanılamadığı
#   için sayı MODELLENMEDİ beyanıyla geri çekilir (sonra_dump.json).
# ===========================================================================
class TestOHD2525DumpSogutmaCeketi:

    #: ÖLÇÜM MOTORU — once_dump.json / sonra_dump.json ile BİRE BİR aynı
    #: kurulum (25 kN RP-1/LOX, çarpışmalı enjektör). Dondurulan sayılar o
    #: dosyalardan gelir; kurulum kayarsa sayılar da kayar.
    TABAN = dict(thrust=25000.0, chamber_pressure=60.0, mixture_ratio=2.5,
                 fuel_type='rp1', oxidizer_type='lox',
                 injector_type='impinging')

    @classmethod
    def _motor(cls, cooling_type):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                m = LRE.LiquidRocketEngine(cooling_type=cooling_type,
                                           overrides={}, **cls.TABAN)
                m.calculate_nozzle_geometry()
        return m

    @classmethod
    def _sogutma(cls, cooling_type):
        m = cls._motor(cooling_type)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return m.calculate_cooling_requirements()

    def test_dump_ceket_debisi_ve_DP_YAYIMLANMAZ(self):
        """Kazanılmamış sayı geri çekilir: None, 0.0 değil.

        0.0 bir ÖLÇÜMDÜR ("akış yok" der); modellenmemiş büyüklüğün yeri
        boştur. Bekçi bu ayrımı ADIYLA ölçer.
        """
        c = self._sogutma('dump_cooling')
        assert c['coolant_flow_rate'] is None
        assert c['cooling_pressure_drop'] is None
        assert c['dump_cooling_jacket_status'] == 'NOT_MODELLED'
        assert c['cooling_channels'] == 0

    def test_dump_kunyesi_REJENERATIF_kunyesini_TASIMAZ(self):
        """Sessiz ikamenin imzası: iki tipin aynı künyeyi taşıması."""
        d = self._sogutma('dump_cooling')
        r = self._sogutma('regenerative')
        assert d['coolant_flow_rate_basis'] == (
            LRE.DUMP_COOLING_BLEED_NOT_MODELLED)
        assert d['coolant_flow_rate_basis'] != r['coolant_flow_rate_basis']
        assert 'regenerative jacket flow' not in d['coolant_flow_rate_basis']
        assert 'NOT MODELLED' in d['coolant_flow_rate_basis']
        assert 'Huzel' in d['coolant_flow_rate_basis'], (
            'hangi modelin eksik olduğu ADIYLA yazılmalı')

    def test_REJENERATIF_ayagi_bozulmadi(self):
        """Geri çekme yalnız dump'ı vurur; diğer tipler ölçülen değerde."""
        r = self._sogutma('regenerative')
        f = self._sogutma('film_cooling')
        assert r['coolant_flow_rate'] == pytest.approx(
            2.561458273760645, rel=1e-12)
        # ÖH A2 sivi-sogutma F-17 (Berke Sunum 2 onayı sonrası yeniden
        # dondurma, denetçi Ş5.6): kanal sayısı tek sığma ölçütünden
        # (41 -> 44) -> ceket ΔP 3,761542589148719 -> 3,30847250671198;
        # debiler bit-aynı.
        # v3.0.5 V305/C1 (28 Eki, ölçüldü, çatal): V301/L-KABUK c80351439
        # (27 Eki 09:04, main'e 6f8240043) rejeneratif cidarı iki katmana
        # ayırdı; kanallar artık 2 mm odacık cidarının değil 1 mm astarın
        # (REGEN_LINER_THICKNESS_M) dışına oturuyor. Kanal tabanı çevresi
        # 2π(29,5508 + 2,0) = 198,24 mm -> 2π(29,5508 + 1,0) = 191,96 mm,
        # sığma ölçütü N·(3 + 1,5) mm ≤ çevre: 44 -> 42 kanal; aynı debi
        # daha az kanaldan geçtiği için ceket ΔP 3,30847250671198 ->
        # 3,6002127648726874. c80351439~1 (688bc30b2) 44 kanal / 3,3085,
        # c80351439 42 kanal / 3,6002 (V305/ci/C1 RAPOR §1). Debi bit-aynı
        # kaldı; bekçinin özü (dump geri çekmesi rejeneratif ayağa
        # dokunmaz) değişmedi, yalnız rejeneratif ayağın kendisi bilinçli
        # olarak yeni cidar modeline geçti.
        assert r['cooling_pressure_drop'] == pytest.approx(
            3.6002127648726874, rel=1e-12)
        assert r['channel_count_fit']['hot_wall_thickness_mm'] == (
            pytest.approx(1.0, rel=1e-12)), (
            'kanal tabanı astar kalınlığında (L-KABUK); çapa ona bağlı')
        # v3.0.1 T-ÇAPA-B: V301/L-B SV-08 — film tipinde rejeneratif ceket
        # YOK (film debisi çekirdeğe EK; L-B RAPOR §SV-08). Eski beklenti
        # film tipinin ceket debisiydi (2,4333853600726125 kg/s); ürün artık
        # o debiyi yayımlamıyor ve nedenini adıyla söylüyor (ölçüldü,
        # 117d704da). Rejeneratif ayak yukarıda bit-aynı.
        assert f['coolant_flow_rate'] is None
        assert f['coolant_flow_rate_basis'].startswith(
            'no regenerative jacket in this cooling type')
        assert r['dump_cooling_jacket_status'] is None
        # V305/C1: 44 -> 42, L-KABUK astar tabanı (yukarıdaki ΔP notu).
        assert r['cooling_channels'] == 42
        assert r['cooling_channels'] == r['channel_count_fit']['n_max']

    def test_dump_ISI_yuku_ve_cidar_zinciri_bozulmadi(self):
        """Geri çekilen ceket ayağıdır; termal yük ve cidar aynen durur."""
        d = self._sogutma('dump_cooling')
        assert d['wall_temperature_hot'] == pytest.approx(850.0, rel=1e-12)
        assert d['wall_temperature_source'] == 'assumed (cooling-type default)'
        assert d['total_heat_load'] > 0

    def test_WALL_TEMP_varsayimi_KAYNAKSIZ_oldugunu_soyler(self):
        """Sabitin kendi künyesi: bu beş sayı bir tablodan gelmiyor."""
        k = LRE.WALL_TEMP_DEFAULT_BASIS
        assert 'UNSOURCED ASSUMPTION' in k
        assert 'not derived from any equation' in k
        assert 'max_wall_temp' in k, 'kullanıcıya çıkış yolu gösterilmeli'
        for tip in ('dump_cooling', 'regenerative', 'film_cooling'):
            assert self._sogutma(tip)['wall_temperature_default_basis'] == k, (
                'künye sayının YANINDA yayımlanmalı')

    def test_kanal_zinciri_None_debiyle_COKMEZ(self):
        """Geri çekilen alan sayısal zincire None olarak sızmamalı.

        ``_design_cooling_lines`` ceket debisini sözlükten okur; alan None
        olduğu için ``or 0.0`` koruması olmasaydı çarpımda TypeError verirdi.
        Dump'ta kanal listesi BOŞ döner (kanal sayısı 0), rejeneratifte dolu.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                d = self._motor('dump_cooling')._design_cooling_lines()
                r = self._motor('regenerative')._design_cooling_lines()
        assert d == []
        assert len(r) > 0, 'rejeneratif kanal zinciri bozulmamalı'


# ===========================================================================
# OH-D30-05 — akustik göç manifestosunun kapsamı
#
# Manifesto dosyası (tests/test_sivi_akustik_gocu.py) 1 Eylül'de "tablo bir
# eski değerler hatırası değil, BUGÜN YENİDEN ÜRETİLEBİLEN bir taban
# ölçümüdür" diyordu. O gün doğruydu; ARTIK GEOMETRİ ALANLARI İÇİN DEĞİL.
# Araya D18/F2 (L* itici çiftine + daralma oranı boğaz çapına bağlandı) ve
# D29/P15B2-10 girdi. Bir manifestonun kendi künyesi bayatlayamaz.
# ===========================================================================
class TestOHD3005GocManifestosu:

    @staticmethod
    def _manifesto():
        return oku(os.path.join(KOK, 'tests', 'test_sivi_akustik_gocu.py'))

    def test_kapsamsiz_iddia_GERI_GELMESIN(self):
        m = self._manifesto()
        assert 'BUGÜN YENİDEN ÜRETİLEBİLEN bir\n#: taban ölçümüdür' not in m
        assert 'OH-D30-05' in m, 'kapsam daraltmasının kimliği dosyada olmalı'
        assert 'GEOMETRİ ALANLARI İÇİN YANLIŞTIR' in m
        assert 'TARİHSEL\n#: TABANDIR' in m or 'TARİHSEL' in m

    def test_daraltma_ADIYLA_iki_kalemi_sayar(self):
        m = self._manifesto()
        for ad in ('BEŞİNCİ SINIF', 'OH-D15-01', 'ALTINCI SINIF',
                   'P15B2-10'):
            assert ad in m, f'{ad} kapsam notunda adıyla geçmeli'

    def test_geometri_kaymasi_dosyanin_KENDI_tablolarindan_olculuyor(self):
        """İddia metinden değil SAYIDAN doğrulanır."""
        import tests.test_sivi_akustik_gocu as GOC
        beklenen = {'ch4_lox_coaxial': -0.430,
                    'rp1_lox_pintle': -0.352,
                    'rp1_lox_impinging': -0.328}
        for ad, hedef in beklenen.items():
            eski = GOC.ONCEKI_B307[ad]['chamber_diameter']
            yeni = GOC.D18_ARA[ad]['chamber_diameter']
            assert (yeni - eski) / eski == pytest.approx(hedef, abs=5e-4), ad

    def test_daralma_orani_12_25_tabani_KALKTI(self):
        import tests.test_sivi_akustik_gocu as GOC
        for ad in ('ch4_lox_coaxial', 'rp1_lox_pintle',
                   'rp1_lox_impinging'):
            eski = GOC.ONCEKI_B307[ad]
            yeni = GOC.D18_ARA[ad]
            cr_eski = (eski['chamber_diameter'] / eski['throat_diameter']) ** 2
            cr_yeni = (yeni['chamber_diameter'] / yeni['throat_diameter']) ** 2
            assert cr_eski == pytest.approx(12.25, abs=5e-3), (
                f'{ad}: tarihsel taban sabit ε_c = 12,25 olmalı')
            assert 3.9 < cr_yeni < 5.6, f'{ad}: yeni daralma oranı {cr_yeni}'
            assert cr_yeni < cr_eski

    def test_termokimya_yapraklari_kapsam_DISINDA_kalmadi(self):
        """Daraltma yalnız GEOMETRİYİ kapsar; iddia termokimyada durur.

        Eşik uydurulmadı: dosyanın kendi iki tablosundan ÖLÇÜLEN sapmalar
        ses hızında 9,6e-5 / 2,7e-4 / 8,0e-4, hazne çapında 0,328 / 0,430 /
        0,352. İki mertebe (en kötü geometri / en kötü termokimya = 410 kat)
        birbirine karışmaz; bekçi bu AYRIMI ölçer, keyfî bir bant değil.
        """
        import tests.test_sivi_akustik_gocu as GOC
        ses, geo = [], []
        for ad in ('ch4_lox_coaxial', 'rp1_lox_pintle',
                   'rp1_lox_impinging'):
            eski, yeni = GOC.ONCEKI_B307[ad], GOC.D18_ARA[ad]
            ses.append(abs(yeni['sound_speed'] - eski['sound_speed'])
                       / eski['sound_speed'])
            geo.append(abs(yeni['chamber_diameter']
                           - eski['chamber_diameter'])
                       / eski['chamber_diameter'])
        assert max(ses) < 1e-3, f'ses hızı sapmaları: {ses}'
        assert min(geo) > 0.3, f'hazne çapı sapmaları: {geo}'
        assert min(geo) / max(ses) > 100, (
            'geometri ile termokimya aynı mertebeye düşerse bu kapsam '
            'daraltmasının gerekçesi ölçümle çürümüş demektir')


# ===========================================================================
# OH-FT-05 — P3B4-11 künyesinin STATİK TABLO yolundaki kilidi
#
# Fable TOPLU sivi-01: TestP3B411ReddedilenYanmaVerimi yalnız RocketCEA
# kolunu görüyor. ÖLÇÜLDÜ (once_ft05.json): o bekçinin kurduğu üç motorun
# ÜÇÜ DE ``combustion_data_source='rocketcea'``; statik tablo kolunun
# (_finalize_performance_reference else-dalı) künyesi hiç koşulmuyor, yani
# oradaki künye anahtar-varlığına geri döndürülse bekçi YEŞİL kalır.
# Onarım o yolda da doğrudur (ölçüldü); eksik olan DÜĞÜMDÜR, o da budur.
#
# Statik kol sahte bir durum değil, ürünün kendi ikinci dağıtım koşuludur:
# RocketCEA kurulu olmayan bir kurulumda cea_bridge statik çapa tablosuna
# düşer ve motor 'warn.liquid.rocketcea_unavailable' uyarısıyla çalışır.
# ===========================================================================
class TestOHFT05StatikTabloYolu:

    @staticmethod
    def _motor(statik, **kw):
        from hrma.engines import cea_bridge
        ovr = dict(expansion_ratio=25.0, burn_time=100.0)
        ovr.update(kw)
        eski = cea_bridge.is_rocketcea_available
        if statik:
            cea_bridge.is_rocketcea_available = lambda: False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    m = LRE.LiquidRocketEngine(
                        thrust=250000.0, chamber_pressure=150.0,
                        mixture_ratio=2.6, fuel_type='rp1',
                        oxidizer_type='lox', overrides=ovr)
                    m.calculate_nozzle_geometry()
        finally:
            cea_bridge.is_rocketcea_available = eski
        return m

    def test_statik_kol_GERCEKTEN_kosuluyor(self):
        """Düğümün kendisi önce kendini kanıtlar: kol gerçekten statik mi?"""
        m = self._motor(statik=True)
        assert m.combustion_data_source == 'static_table'
        assert any(w['code'] == 'warn.liquid.rocketcea_unavailable'
                   for w in m.design_warnings)
        assert self._motor(statik=False).combustion_data_source == 'rocketcea'

    def test_STATIK_yolda_reddedilen_verim_kunyesi_TEK_kaynaktan(self):
        """OH-FT-05'in kilitlediği asıl düğüm."""
        m = self._motor(statik=True, combustion_efficiency=300.0)
        assert float(m.eta_c_star) == pytest.approx(1.0, rel=1e-12)
        de = m._delivered_eff or {}
        assert 'not supplied' in de['eta_c_star_source'], (
            'bandın dışında kalan girdi REDDEDİLDİ; künye onu "user input" '
            'diye yayımlayamaz (anahtar VARLIĞI kabul demek değildir)')
        assert de['eta_c_star_source'] == m.eta_c_star_source
        assert any(w['code'] == 'warn.liquid.input_out_of_range'
                   for w in m.design_warnings)

    def test_STATIK_yolda_kabul_edilen_girdi_kullanici_girdisi_der(self):
        m = self._motor(statik=True, combustion_efficiency=90.0)
        assert float(m.eta_c_star) == pytest.approx(0.90, rel=1e-12)
        de = m._delivered_eff or {}
        assert de['eta_c_star_source'] == 'user input (combustion efficiency)'
        assert de['eta_c_star_source'] == m.eta_c_star_source

    def test_STATIK_yolda_lule_kaybi_CIFT_sayilmaz(self):
        """Statik kolun kendi sözleşmesi: tablo zaten teslim seviyesindedir."""
        de = self._motor(statik=True, combustion_efficiency=90.0
                         )._delivered_eff or {}
        assert de['eta_nozzle'] == 1.0
        assert de['eta_isp'] == pytest.approx(0.90, rel=1e-12)
        assert 'double counting' in de['model']


# ===========================================================================
# B4-10 — power_residual_rel bir ölçüm mü, cebirsel özdeşlik mi?
#
# BAŞLIK KISMEN ÇÜRÜTÜLDÜ (once_b410.json, taban ağacı): "altı çevrimin
# altısında TAM SIFIR" bugün doğru DEĞİL. Ölçülen:
#   gas_generator 0,0            tap_off 0,0              -> 2 çevrim tam sıfır
#   staged 1,02e-15              FFSC 4,55e-15            -> makine epsilonu
#   pressure_fed None            (D20 onarımı duruyor: mil yok, hüküm yok)
#   expander (yakınsamadı) nan   -> D20 onarımının KAPSAMA BOŞLUĞU
# Başlığın ÖZÜ ise ayakta: sayı çözücünün kendi yakınsama artığıdır, ikinci
# bir modele karşı doğrulama değildir (0,0 ile 1e-15 arasındaki fark yalnız
# kayan nokta yuvarlamasıdır, doğruluk farkı değildir).
#
# BU DALGADA ONARILAN İKİ AYAK:
#   (1) yakınsamayan çevrim nan yayımlıyordu -> None (fail-closed);
#   (2) mil başına döküm artığı ÇIPLAK yayımlıyordu (5 mil) -> künye yanında.
# ONARILAMAYAN AYAK: artığı gerçek bir çapraz denetime çevirmek türbin/pompa
# güçlerini İKİNCİ BAĞIMSIZ bir modelden türetmeyi gerektirir (gerçek-gaz
# türbin işi ⟷ ideal Δh) -> ÖK-06, fizik dalgası. Aynı denklemi iki kez
# çözmek bağımsızlık değildir; o yüzden uydurulmadı.
# ===========================================================================
class TestB410GucArtigi:

    TABAN = dict(pc_bar=100.0, mdot_total=80.0, mr=2.6, fuel='rp1',
                 oxidizer='lox')

    @classmethod
    def _coz(cls, tip, **kw):
        from hrma.engines import cycle_power_balance as CPB
        p = dict(cls.TABAN)
        p.update(kw)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return CPB.solve_cycle(tip, **p)

    def test_YAKINSAMAYAN_cevrim_artigi_YAYIMLAMAZ(self):
        """nan bir sayı gibi okunur; kapanmamış denge için hüküm yoktur."""
        sol = self._coz('expander', fuel='methane', regen_heat_kw=9000.0)
        assert sol.converged is False, (
            'ölçüm motoru yakınsamamalıydı; girdiler kaymışsa bu bekçi '
            'kusuru göremez')
        assert sol.power_residual_rel is None
        assert not (isinstance(sol.power_residual_rel, float)
                    and math.isnan(sol.power_residual_rel))

    def test_yanit_KATI_JSON_ayristiricisindan_gecer(self):
        """nan geçerli JSON değildir: katı istemci yanıtın TAMAMINI reddeder."""
        sol = self._coz('expander', fuel='methane', regen_heat_kw=9000.0)
        # ÖH D31 fix-34a: İDDİA GÖVDEYE YAZILDI. ``allow_nan=False`` tek
        # başına kapıydı ama gövdede ``assert`` yoktu, bu yüzden OH-D29-12
        # delegesiz envanteri bu testi "iddiasız" sayıyordu (tavan 51/51
        # DOLU, ÖK-22 gereği yükseltilemez -> çözüm envantere satır değil
        # teste iddia). İkinci ayak ölçülen bir kaçağı kapatır:
        # ``default=str`` sonlu olmayan bir değeri DİZEYE çevirirse
        # ``allow_nan`` kapısı hiç görmez ve katı istemci gövdeyi kabul
        # eder — o zaman "nan yayımlanmadı" sahte bir yeşil olur.
        metin = json.dumps(sol.to_dict(), allow_nan=False, default=str)
        kacak = [im for im in ('"nan"', '"inf"', '"-inf"', '"NaN"',
                               '"Infinity"', '"-Infinity"') if im in metin]
        assert not kacak, (
            'sonlu olmayan değer DİZEYE çevrilip katı ayrıştırıcıdan '
            'geçirilmiş: %s' % kacak)

    def test_MILSIZ_cevrim_D20_onarimi_duruyor(self):
        """Devir denetimi: önceki dalganın onarımı yerinde mi."""
        sol = self._coz('pressure_fed')
        assert sol.power_residual_rel is None
        assert sol.shafts == []

    def test_mil_basina_artik_CIPLAK_yayimlanmaz(self):
        """ÖLÇÜLDÜ: tabanda 5 mil künyesiz sayı yayımlıyordu."""
        from hrma.engines import cycle_power_balance as CPB
        kunyesiz = 0
        for tip, kw in (('gas_generator', dict(tit_K=800.0)),
                        ('staged_combustion', dict(tit_K=800.0)),
                        ('tap_off', dict(tit_K=800.0)),
                        ('full_flow_staged_combustion', dict(tit_K=800.0))):
            sol = self._coz(tip, **kw)
            assert sol.shafts, tip
            for mil in sol.shafts:
                assert mil['power_residual_rel'] is not None, tip
                if not mil.get('power_residual_basis'):
                    kunyesiz += 1
                else:
                    assert (mil['power_residual_basis']
                            == CPB.SHAFT_RESIDUAL_BASIS)
        assert kunyesiz == 0, f'{kunyesiz} mil künyesiz sayı yayımlıyor'

    def test_kunye_BAGIMSIZ_DOGRULAMA_DEGIL_dedigini_soyler(self):
        """Kalemin özü: sayı bir çapraz denetim sanılmamalı."""
        from hrma.engines import cycle_power_balance as CPB
        ust = CPB.CycleSolution(cycle_type='gas_generator'
                                ).power_residual_basis
        mil = CPB.SHAFT_RESIDUAL_BASIS
        for k in (ust, mil):
            assert 'not an independent cross-check' in k
            assert 'convergence residual' in k
            assert 'second model' in k
        assert 'did not converge' in ust, (
            'null gerekçesi yalnız "mil yok" değil, "yakınsamadı" da olmalı')

    def test_basligin_TAM_SIFIR_iddiasi_bugun_OLCULEN_haliyle_donduruldu(self):
        """Çürütme kaydı: 6/6 tam sıfır DEĞİL, 2 tam sıfır + 2 epsilon.

        Sayılar dondurulmaz (platform kayar); dondurulan SINIFLANDIRMADIR.
        Artık makine epsilonunun üstüne çıkarsa çözücü bozulmuş demektir.
        """
        olculen = {
            'gas_generator': dict(tit_K=800.0),
            'tap_off': dict(tit_K=800.0),
            'staged_combustion': dict(tit_K=800.0),
            'full_flow_staged_combustion': dict(tit_K=800.0),
        }
        tam_sifir, epsilon = 0, 0
        for tip, kw in olculen.items():
            r = self._coz(tip, **kw).power_residual_rel
            assert r is not None and r >= 0.0, tip
            if r == 0.0:
                tam_sifir += 1
            else:
                assert r < 1e-12, f'{tip}: artık {r} makine epsilonunun üstünde'
                epsilon += 1
        assert tam_sifir + epsilon == 4
        assert tam_sifir >= 1, (
            'hiçbir çevrimde tam sıfır çıkmıyorsa başlığın çürütme ölçümü '
            'yeniden yapılmalı')

    def test_bagimsiz_ikinci_model_BORCU_kodda_ADIYLA_duruyor(self):
        """ÖK-06 borcu sessizce kapanmış gibi görünmesin."""
        kaynak = oku(os.path.join(
            KOK, 'hrma', 'engines', 'cycle_power_balance.py'))
        assert 'B4-10' in kaynak
        assert 'not an independent cross-check' in kaynak


# ===========================================================================
# OH-D21-09 — Rao λ araması (KAYIT) + statüko kilidi
#
# Kalem "belgelenmiş Rao λ tablosu bulunursa oran yerine tablo" diyor. Arama
# D31'de KAYITLI olarak tekrarlandı (rao_lambda_arama_kaydi.md): depoda λ
# tablosu taşıyan veri dosyası yok; literatürde de λ kontur yüzdesi cinsinden
# TABLOLANMIYOR -- tablolanan büyüklük kontur AÇILARIDIR (θ_n, θ_e) ve λ
# onlardan türetilir. Yani "oran yerine tablo" seçeneği aranan biçimde
# mevcut değil: tablolanan büyüklük ürünün zaten GİRDİ olarak kullandığı
# büyüklüktür. Ürün davranışı DEĞİŞTİRİLMEDİ; bu sınıf statükoyu kilitler.
# ===========================================================================
class TestOHD2109RaoLambdaArama:

    @staticmethod
    def _motor(nozzle_type):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                m = LRE.LiquidRocketEngine(
                    thrust=250000.0, chamber_pressure=150.0,
                    mixture_ratio=2.6, fuel_type='rp1', oxidizer_type='lox',
                    overrides=dict(expansion_ratio=25.0, burn_time=100.0,
                                   nozzle_type=nozzle_type))
                m.calculate_nozzle_geometry()
        return m

    def test_kontur_ACILARI_duruyor_TABLONUN_girdisi_bunlar(self):
        """Rao literatürünün tabloladığı büyüklük: θ_n ve θ_e."""
        g = LRE.NOZZLE_TYPE_GEOMETRY
        assert (g['bell_80']['half_angle'], g['bell_80']['exit_angle']) == (
            30.0, 8.5)
        assert (g['bell_60']['half_angle'], g['bell_60']['exit_angle']) == (
            34.0, 12.0)
        assert g['bell_60']['length_fraction'] == 0.60
        assert g['bell_80']['length_fraction'] == 0.80

    def test_ORAN_yontemi_duruyor_ve_referans_kontur_DEGISMEDI(self):
        """Sözleşme: referans kontur yayımlanan λ'yı AYNEN alır, başkası
        eşdeğer-koni ORANI kadar düzeltilir (ölçüldü: bell_60 -> 0,987869)."""
        assert LRE.LAMBDA_BELL_REFERENCE_CONTOUR == 'bell_80'
        assert float(LRE.LAMBDA_BELL) == 0.985

        def lam_koni(g):
            a = 0.5 * (g['half_angle'] + g['exit_angle'])
            return (1.0 + math.cos(math.radians(a))) / 2.0

        ref = LRE.NOZZLE_TYPE_GEOMETRY[LRE.LAMBDA_BELL_REFERENCE_CONTOUR]
        oran60 = lam_koni(LRE.NOZZLE_TYPE_GEOMETRY['bell_60']) / lam_koni(ref)
        assert oran60 == pytest.approx(0.987869, abs=1e-6)
        assert oran60 < 1.0, 'kısa çan referanstan daha çok sapma kaybeder'
        assert float(LRE.LAMBDA_BELL) * oran60 == pytest.approx(
            0.973051, abs=1e-6)

    def test_kunye_TABLO_DEGIL_dedigini_KORUYOR(self):
        """Kalem kapanmadıkça bu ibare sessizce silinemez."""
        k = LRE.LAMBDA_BELL_CONTOUR_SOURCE
        assert 'APPROXIMATE' in k
        assert 'not a Rao table' in k
        assert 'equivalent-cone RATIO' in k

    def test_bell60_ile_bell80_AYIRT_EDILEBILIR_kaldi(self):
        """OH-D20-02 onarımının devir denetimi: iki kontur aynı sayıyı almaz."""
        i80 = float(self._motor('bell_80').isp_vac)
        i60 = float(self._motor('bell_60').isp_vac)
        assert i60 != i80
        assert i60 < i80, 'kısa çan daha çok sapma kaybeder'

    def test_statuko_OLCULEN_maliyetiyle_donduruldu(self):
        """Kalem başlığındaki %1,21 bugün de ölçülüyor mu (çürüdü mü)?"""
        i80 = float(self._motor('bell_80').isp_vac)
        i60 = float(self._motor('bell_60').isp_vac)
        assert i80 == pytest.approx(333.2237, abs=5e-3)
        assert i60 == pytest.approx(329.1813, abs=5e-3)
        assert (i60 - i80) / i80 == pytest.approx(-0.012131, abs=5e-6)

    def test_arama_KAYDI_dosyada_duruyor(self):
        """Bulunamayan tablo bir kayıt bırakır; kalem sessizce kapanmaz."""
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D31',
                           'sivi', 'a1', 'rao_lambda_arama_kaydi.md')
        assert os.path.exists(kanit_gerekli(yol)), 'kayıtlı arama dosyası silinmiş'
        kayit = oku(kanit_gerekli(yol))
        for parca in ('OH-D21-09', 'KAYIT', 'kismen', 'NOZZLE_TYPE_GEOMETRY',
                      '333,2237', '329,1813'):
            assert parca in kayit, parca
