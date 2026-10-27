"""Kitap uyum p1a — B16 (Ö-1): hibrit N₂O giriş durumu, sıvı entalpisi.

Kalem (KARS-S kitap uyum girdisi, 6 Eki 2026; karar §28, Berke §5 soru 1
önerisi): kendinden basınçlı hibritte sıvı N₂O 298 K ideal GAZ entalpisiyle
(+82,05 kJ/mol) yakılıyordu. Artık oksitleyici giriş durumu GİRDİDİR
(sıcaklık = ``tank_temperature``, faz = ``oxidizer_phase``); varsayılan
293,15 K doymuş sıvıdır; yöntem RP-1311 §4.1 (atanmış entalpi).

Bekçiler (her biri için ters mutasyon: docs/scofield/raw/OH/KITAP/p1a/
mutasyon.md):

* kâhin — 293,15 K değeri CoolProp'un BAĞIMSIZ yolundan (düşük yoğunluk
  limiti, ``PropsSI('Hmolar', 'T', 298,15, 'Dmolar', ε)``) yeniden üretilir;
  NKN'de RocketCEA 'N2O_nbp' kartının düzeltmesiyle, ΔvapH(NKN) Atake-Chihara
  kalorimetrisiyle tutarlı;
* bağımsız çözücü — c* değişiminin yönü ve büyüklüğü NASA CEA (RocketCEA)
  ile;
* 'gas' fazı kalem öncesi reaktan entalpisini BİT-ÖZDEŞ verir;
* fail-closed — kritik nokta üstü / üçlü nokta altı / sonlu olmayan sıcaklık
  ve bilinmeyen faz açık hatayla reddedilir;
* bayat önbellek yasağı — analizörün denge önbelleği, motorun c*(O/F) ızgara
  önbelleği ve modül düzeyi optimum O/F önbelleği giriş durumunu ayırır;
* beyan — ``oxidizer_inlet_state`` alanı.

Ağ KAPALI (RocketCEA yerel Fortran; CoolProp yerel).
"""
import contextlib
import io
import math
import socket

import pytest

from hrma.engines import oxidizer_inlet as oi
from hrma.engines.combustion_analysis import (
    CombustionAnalyzer, _OPTIMUM_OF_CACHE)
from hrma.data.propellant_database import (
    N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL as HF_GAZ)

CoolProp = pytest.importorskip('CoolProp.CoolProp')

#: Bağımsız referans değerler (yalnız testte; ürün kodunda yok).
#: Atake & Chihara (1974), kalorimetrik ΔvapH N₂O @ 184,7 K — NIST
#: Chemistry WebBook faz değişimi verisi (KARS-TK bulgu 16 §3; yerel kopya
#: yok, sayfa doğrulanmadı).
ATAKE_CHIHARA_DVAP_KJ_MOL = 16.5
#: Atake-Chihara tek ondalıkla verildiği için yarım birim tolerans.
ATAKE_CHIHARA_TOL_KJ_MOL = 0.05
#: Sentez ölçütü (KARS-TK bulgu 16, CoolProp 293,15 K, JANAF tabanı).
SENTEZ_293K_KJ_MOL = 70.82


@pytest.fixture(autouse=True)
def _ag_kapali(monkeypatch):
    def _ret(*a, **k):
        raise OSError('test_kitap_p1a: ağ kapalı')
    monkeypatch.setattr(socket.socket, 'connect', _ret)
    monkeypatch.setattr(socket, 'create_connection', _ret)


def _analizci(memoize=False):
    with contextlib.redirect_stdout(io.StringIO()):
        return CombustionAnalyzer(memoize=memoize)


def _bagimsiz_duzeltme_kj_mol(T):
    """h_doymuş_sıvı(T) − h_ig(298,15) — ürün kodundan BAĞIMSIZ yol.

    Ürün h_ig'yi α⁰ türevinden okur; burada düşük yoğunluk limiti
    kullanılır (artık entalpi ρ → 0'da sıfıra gider).
    """
    PropsSI = CoolProp.PropsSI
    h_ig = PropsSI('Hmolar', 'T', 298.15, 'Dmolar', 1e-6, 'N2O')
    h_l = PropsSI('Hmolar', 'T', T, 'Q', 0, 'N2O')
    return (h_l - h_ig) / 1000.0


# ---------------------------------------------------------------------------
# Kâhin
# ---------------------------------------------------------------------------
class TestKahin:
    def test_293K_sivi_bagimsiz_yoldan_ayni(self):
        durum = oi.n2o_inlet_state(293.15, 'liquid')
        beklenen = HF_GAZ + _bagimsiz_duzeltme_kj_mol(293.15)
        assert durum['formation_enthalpy_kJ_mol'] == pytest.approx(
            beklenen, abs=1e-6)
        # Sentezin iddiası (70,82) kendi hesabımızla aynı ondalıkta.
        assert round(durum['formation_enthalpy_kJ_mol'], 2) == (
            SENTEZ_293K_KJ_MOL)

    def test_nkn_rocketcea_n2o_nbp_kartiyla_tutarli(self):
        """RocketCEA 'N2O_nbp' kartı (184,4 K) ile düzeltme çapraz denetimi.

        Kartın kendi düzeltmesi = h(N2O_nbp) − h(N2O gaz kartı). İki kart
        aynı kütüphaneden, ürün kodundan bağımsız.
        """
        ic = pytest.importorskip('rocketcea.input_cards')
        kartlar = ic.oxCards

        def _h_kj(ad):
            metin = ' '.join(kartlar[ad])
            cal = float(metin.split('h,cal=')[1].split()[0])
            T = float(metin.split('t(k)=')[1].split()[0])
            return cal * 4.184 / 1000.0, T

        h_gaz, _ = _h_kj('N2O')
        h_nbp, T_nbp = _h_kj('N2O_nbp')
        kart_duzeltme = h_nbp - h_gaz
        urun = oi.n2o_inlet_state(T_nbp, 'liquid')['enthalpy_correction_kJ_mol']
        # Kart düzeltmesi −20,43; EOS −20,67 (0,24 kJ/mol = %1,2). Kart
        # gaz değeri (81,45) ile thermo.inp gazı (Gurvich 81,60) ayrı
        # değerlendirmelerdir; tolerans bu iç farkın iki katı.
        assert urun == pytest.approx(kart_duzeltme, abs=0.3)
        assert urun < 0.0 and kart_duzeltme < 0.0

    def test_nkn_buharlasma_isisi_atake_chihara_ile_tutarli(self):
        PropsSI = CoolProp.PropsSI
        T_nkn = PropsSI('T', 'P', 101325.0, 'Q', 0, 'N2O')
        dvap = (PropsSI('Hmolar', 'T', T_nkn, 'Q', 1, 'N2O')
                - PropsSI('Hmolar', 'T', T_nkn, 'Q', 0, 'N2O')) / 1000.0
        assert dvap == pytest.approx(ATAKE_CHIHARA_DVAP_KJ_MOL,
                                     abs=ATAKE_CHIHARA_TOL_KJ_MOL)

    def test_duzeltme_sicaklikla_monoton(self):
        """Daha soğuk sıvı daha az enerji taşır (duyulur ısı)."""
        degerler = [oi.n2o_inlet_state(T, 'liquid')[
            'formation_enthalpy_kJ_mol'] for T in (200.0, 253.15, 273.15,
                                                   293.15, 305.0)]
        assert degerler == sorted(degerler)
        assert all(v < HF_GAZ for v in degerler)


class TestBagimsizCozucu:
    """NASA CEA (RocketCEA Fortran) ile c* değişiminin yönü ve büyüklüğü."""

    def test_c_star_degisimi_cea_ile_ayni_yonde_ve_buyuklukte(
            self, tmp_path, monkeypatch):
        cm = pytest.importorskip('rocketcea.cea_obj')
        # V3 kararlılık K-3: süreç-global veri dizini test sonunda GERİ
        # alınır (monkeypatch). Geri alınmayınca aynı süreçte sonra koşan
        # test_faz5_motor::TestCeaProcessIsolation::test_data_dir_is_process_local
        # kırmızıya dönüyordu (12 Eki dilim 0).
        monkeypatch.setattr(cm, 'ROCKETCEA_DATA_DIR', cm.ROCKETCEA_DATA_DIR)
        cm.set_rocketcea_data_dir(str(tmp_path), do_print=False)
        ic = pytest.importorskip('rocketcea.input_cards')
        metin = ' '.join(ic.oxCards['N2O'])
        h_gaz_kart = float(metin.split('h,cal=')[1].split()[0]) * 4.184e-3
        duzeltme = oi.n2o_inlet_state(293.15)['enthalpy_correction_kJ_mol']
        cm.add_new_oxidizer(
            'N2O_P1A_L293',
            ' oxid NitrousOxide N 2.0 O 1.0 wt%=100.00 \n'
            f' h,kj={h_gaz_kart + duzeltme:.4f} t(k)=293.15 ')
        psia = 30.0 / 0.0689475729
        cs_gaz = cm.CEA_Obj(oxName='N2O', fuelName='HTPB').get_Cstar(
            Pc=psia, MR=6.0)
        cs_siv = cm.CEA_Obj(oxName='N2O_P1A_L293', fuelName='HTPB').get_Cstar(
            Pc=psia, MR=6.0)
        cea_pct = 100.0 * (cs_siv / cs_gaz - 1.0)

        ca = _analizci()
        once = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, None,
                                     expansion_ratio=5.0)
        ca.set_oxidizer_inlet_state(None, 'gas')
        gaz = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, None,
                                    expansion_ratio=5.0)
        hrma_pct = 100.0 * (once['performance']['c_star']
                            / gaz['performance']['c_star'] - 1.0)
        assert cea_pct < 0.0 and hrma_pct < 0.0
        # Ölçülen: CEA −%1,34 ⟷ HRMA −%1,43 (iki ayrı veri tabanı).
        assert hrma_pct == pytest.approx(cea_pct, abs=0.25)


# ---------------------------------------------------------------------------
# 'gas' fazı = kalem öncesi davranış (bit-özdeş)
# ---------------------------------------------------------------------------
class TestGazBitOzdes:
    def test_gaz_reaktan_entalpisi_bit_ozdes(self):
        ca = _analizci()
        ca.set_oxidizer_inlet_state(None, 'gas')
        h = ca._calculate_reactant_enthalpy({'htpb': 100.0}, 'n2o', 6.0)
        spec_y = ca.propellant_specs['htpb']
        spec_o = ca.propellant_specs['n2o']
        h_yakit = 1.0 * spec_y['enthalpy_formation'] * 1e6 / (
            spec_y['molecular_weight'])
        eski = (1.0 / 7.0) * h_yakit + (6.0 / 7.0) * (
            HF_GAZ * 1e6 / spec_o['molecular_weight'])
        assert h == eski  # eşitlik, yaklaşık değil

    def test_gaz_fazi_sicakligi_uygulamaz(self):
        a = oi.n2o_inlet_state(250.0, 'gas')
        b = oi.n2o_inlet_state(300.0, 'gas')
        assert a['formation_enthalpy_kJ_mol'] == b['formation_enthalpy_kJ_mol']
        assert a['formation_enthalpy_kJ_mol'] == HF_GAZ
        assert a['temperature_applied'] is False

    def test_gaz_tam_sonuc_esit_ve_sivi_daha_soguk(self):
        ca = _analizci()
        sivi = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, None,
                                     expansion_ratio=5.0)
        ca.set_oxidizer_inlet_state(273.15, 'gas')
        gaz1 = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, None,
                                     expansion_ratio=5.0)
        ca2 = _analizci()
        ca2.set_oxidizer_inlet_state(None, 'gas')
        gaz2 = ca2.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, None,
                                      expansion_ratio=5.0)
        assert gaz1['performance'] == gaz2['performance']
        T_s = sivi['compositions']['chamber']['temperature']
        T_g = gaz1['compositions']['chamber']['temperature']
        assert T_g - T_s == pytest.approx(66.4, abs=2.0)


# ---------------------------------------------------------------------------
# Fail-closed
# ---------------------------------------------------------------------------
class TestFailClosed:
    # 2. tur, denetçi şartı Ş-1 (D4): üçlü nokta altı ('182', '50') ÜRÜNÜN
    # KENDİ kapısının mesajını bekler. 1. turda yalnız ``ValueError``
    # bekleniyordu ve üçlü nokta kapısı kapatıldığında da test yeşil
    # kalıyordu: CoolProp kendi ValueError'ını atıyor (QT_flash aralığı
    # 182,23–309,52 K). Ters mutasyon: mutasyon.md.
    @pytest.mark.parametrize('T, mesaj', [
        (309.52, 'critical temperature'), (320.0, 'critical temperature'),
        (182.0, 'triple point'), (50.0, 'triple point'),
        (float('nan'), 'finite number'), (float('inf'), 'finite number'),
        ('yirmi', 'finite number'), (True, 'finite number')],
        ids=['Tkrit', '320', '182', '50', 'nan', 'inf', 'metin', 'bool'])
    def test_gecersiz_sivi_sicakligi_reddedilir(self, T, mesaj):
        with pytest.raises(ValueError, match=mesaj):
            oi.n2o_inlet_state(T, 'liquid')

    def test_kritik_sinir_coolproptan(self):
        T_uclu, T_kritik = oi.n2o_saturation_envelope_k()
        assert T_kritik == CoolProp.PropsSI('Tcrit', 'N2O')
        assert T_uclu == CoolProp.PropsSI('Ttriple', 'N2O')
        with pytest.raises(ValueError, match='saturated-liquid envelope'):
            oi.n2o_inlet_state(T_kritik, 'liquid')
        oi.n2o_inlet_state(T_kritik - 0.5, 'liquid')  # içeride çözülür

    @pytest.mark.parametrize('faz', ['gaseous', 'sıvı', '', 'plasma', 3],
                             ids=['gaseous', 'sivi_tr', 'bos', 'plasma', 'int'])
    def test_bilinmeyen_faz_reddedilir(self, faz):
        with pytest.raises(ValueError, match='phase'):
            oi.normalize_inlet_phase(faz)

    def test_hatali_ayar_durumu_degistirmez(self):
        ca = _analizci()
        ca.set_oxidizer_inlet_state(273.15, 'liquid')
        once = ca.oxidizer_inlet_state('n2o')
        with pytest.raises(ValueError):
            ca.set_oxidizer_inlet_state(330.0, 'liquid')
        assert ca.oxidizer_inlet_state('n2o') == once

    def test_motor_kurucusu_bilinmeyen_fazi_adiyla_reddeder(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with pytest.raises(ValueError, match='phase'):
            HybridRocketEngine(thrust=1000, burn_time=5, chamber_pressure=20,
                               oxidizer_phase='plasma')

    def test_motor_kritik_ustu_tank_sicakligini_reddeder(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = HybridRocketEngine(thrust=1000, burn_time=5, chamber_pressure=20,
                               of_ratio=6.0, tank_temperature=315.0)
        with pytest.raises(ValueError, match='saturated-liquid envelope'):
            m._sync_oxidizer_inlet_state()


# ---------------------------------------------------------------------------
# Bayat önbellek yasağı
# ---------------------------------------------------------------------------
class TestOnbellek:
    def test_analizci_denge_onbellegi_giris_durumunu_ayirir(self):
        ca = _analizci(memoize=True)
        args = ({'htpb': 100.0}, 'n2o', 6.0, 30.0, None)
        a = ca.analyze_combustion(*args)['performance']['c_star']
        ca.set_oxidizer_inlet_state(273.15, 'liquid')
        b = ca.analyze_combustion(*args)['performance']['c_star']
        ca.set_oxidizer_inlet_state(None, 'gas')
        c = ca.analyze_combustion(*args)['performance']['c_star']
        ca.set_oxidizer_inlet_state(None, None)
        d = ca.analyze_combustion(*args)['performance']['c_star']
        assert b < a < c
        assert d == a  # varsayılana dönüş kendi hücresini bulur

    def test_motor_cstar_izgarasi_giris_durumunu_ayirir(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = HybridRocketEngine(thrust=1000, burn_time=5, chamber_pressure=20,
                               of_ratio=6.0)
        c_293, _ = m._instantaneous_performance(6.0)
        m.tank_temperature = 273.15
        c_273, _ = m._instantaneous_performance(6.0)
        m.oxidizer_phase = 'gas'
        c_gaz, _ = m._instantaneous_performance(6.0)
        assert c_273 < c_293 < c_gaz

    # 2. tur, denetçi şartı Ş-5 (karar §28-18): 1. turdaki yalıtım bağlamı
    # (önbelleği geçici boşaltan ``clear``/``update``) waitress threads=4
    # altında yarışa açıktı ve kaldırıldı; anahtar artık giriş imzasını
    # taşır. Aşağıdaki iki bekçi bunu korur. Ters mutasyon (imza anahtardan
    # çıkarılır) ikisini de KIRMIZI yapar: mutasyon.md.
    def test_optimum_of_anahtari_giris_imzasini_tasir(self):
        _OPTIMUM_OF_CACHE.clear()
        yakit = {'htpb': 100.0}
        ca = _analizci()
        v = ca.find_optimum_of_ratio(yakit, 'n2o', 25.0)
        cb = _analizci()
        cb.set_oxidizer_inlet_state(None, 'gas')
        g = cb.find_optimum_of_ratio(yakit, 'n2o', 25.0)
        cc = _analizci()
        cc.set_oxidizer_inlet_state(273.15, 'liquid')
        s = cc.find_optimum_of_ratio(yakit, 'n2o', 25.0)
        # Aynı diğer anahtar, üç giriş durumu → üç AYRI önbellek girdisi…
        assert len(_OPTIMUM_OF_CACHE) == 3
        # …ve her biri kendi durumunun sonucu (gaz en sıcak, 273 K sıvı en
        # soğuk; varsayılanın hücresi okunmadı).
        assert s['maximum_isp'] < v['maximum_isp'] < g['maximum_isp']
        # İsabet de durum başınadır: varsayılan tekrar sorulunca kendi
        # (ilk) sonucunu alır, sonradan eklenen girdiler onu ezmez.
        assert ca.find_optimum_of_ratio(yakit, 'n2o', 25.0) == v
        # İmza HP dengesine FİİLEN giren entalpiyi taşır.
        assert cc.optimum_of_inlet_signature('n2o')[2] == pytest.approx(
            cc.oxidizer_inlet_state('n2o')['formation_enthalpy_kJ_mol'])
        assert ca.optimum_of_inlet_signature('lox') == (
            cc.optimum_of_inlet_signature('lox'))
        _OPTIMUM_OF_CACHE.clear()

    def test_optimum_of_esanli_iki_giris_durumu_birbirini_okumaz(self):
        """İki iş parçacıklı yarış (waitress threads=4 benzetimi).

        Her tur önbellek BOŞKEN iki işçi aynı anda (Barrier) aynı diğer
        anahtarla arar: biri varsayılan sıvı, öteki 'gas'. Her işçi kendi
        durumunun SERİ referansını almalıdır; ardından aynı aramalar önbellek
        isabetinden de doğru dönmelidir. Seri referanslar önbellek
        temizlenerek ayrı ayrı hesaplanır.
        """
        import threading
        yakit = {'htpb': 100.0}
        durumlar = {'sivi': (None, None), 'gaz': (None, 'gas')}
        referans = {}
        for ad, (T, faz) in durumlar.items():
            _OPTIMUM_OF_CACHE.clear()
            a = _analizci()
            a.set_oxidizer_inlet_state(T, faz)
            referans[ad] = a.find_optimum_of_ratio(yakit, 'n2o', 25.0)
        assert referans['sivi'] != referans['gaz']
        analizciler = {}
        for ad, (T, faz) in durumlar.items():
            analizciler[ad] = _analizci()
            analizciler[ad].set_oxidizer_inlet_state(T, faz)
        for _tur in range(2):
            _OPTIMUM_OF_CACHE.clear()
            for _gecis in range(2):  # 1: taze hesap yarışı, 2: isabet yarışı
                engel = threading.Barrier(len(durumlar))
                sonuc, hata = {}, []

                def _isci(ad):
                    try:
                        engel.wait(timeout=60)
                        sonuc[ad] = analizciler[ad].find_optimum_of_ratio(
                            yakit, 'n2o', 25.0)
                    except Exception as exc:  # pragma: no cover - teşhis
                        hata.append((ad, repr(exc)))

                isciler = [threading.Thread(target=_isci, args=(ad,))
                           for ad in durumlar]
                for t in isciler:
                    t.start()
                for t in isciler:
                    t.join(timeout=300)
                assert not hata, hata
                for ad in durumlar:
                    assert sonuc[ad] == referans[ad], (ad, _tur, _gecis)
        _OPTIMUM_OF_CACHE.clear()


# ---------------------------------------------------------------------------
# Beyan
# ---------------------------------------------------------------------------
class TestBeyan:
    def test_varsayilan_beyan(self):
        ca = _analizci()
        b = ca.oxidizer_inlet_state('n2o')
        assert b['phase'] == 'liquid'
        assert b['temperature_K'] == oi.default_inlet_temperature_k()
        assert b['inlet_state_source'] == 'default'
        for alan in ('formation_enthalpy_kJ_mol', 'method', 'source',
                     'gas_reference_formation_enthalpy_kJ_mol'):
            assert b[alan] not in (None, '')
        assert 'RP-1311' in b['method']
        assert 'Lemmon' in b['source']

    def test_lox_sabit_referans_beyani(self):
        b = _analizci().oxidizer_inlet_state('lox')
        assert b['status'] == 'fixed_reference'
        assert b['temperature_applied'] is False

    def test_motor_yaniti_beyani_tasir(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with contextlib.redirect_stdout(io.StringIO()):
            m = HybridRocketEngine(thrust=1000, burn_time=5,
                                   chamber_pressure=20, of_ratio=6.0,
                                   tank_temperature=273.15)
            r = m.calculate()
        b = r['oxidizer_inlet_state']
        assert b['temperature_K'] == 273.15
        assert b['phase'] == 'liquid'
        assert b['inlet_temperature_source'] == 'user input (tank_temperature)'
        assert b['inlet_phase_source'] == 'default (saturated liquid)'
        assert b['formation_enthalpy_kJ_mol'] == pytest.approx(
            HF_GAZ + _bagimsiz_duzeltme_kj_mol(273.15), abs=1e-6)
        # Beyan edilen entalpi gerçekten yakılan entalpidir: motorun T_c'si
        # aynı giriş durumundaki bağımsız analizörle aynı.
        ca = _analizci()
        ca.set_oxidizer_inlet_state(273.15, 'liquid')
        ref = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0, None)
        assert m.T_c == ref['compositions']['chamber']['temperature']


    def test_ampirik_zarfta_entered_equilibrium_false(self):
        """2. tur, denetçi şartı Ş-2 (D8): ampirik zarfa düşen yakıtta
        (aluminum) beyan, giriş entalpisinin T_c'ye GİRMEDİĞİNİ söyler.

        1. turda bu yol test edilmiyordu; ``entered_equilibrium`` sabit True
        yapıldığında bekçiler yeşil kalıyordu. Ters mutasyon: mutasyon.md.
        """
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with contextlib.redirect_stdout(io.StringIO()):
            m = HybridRocketEngine(thrust=1000, burn_time=5,
                                   chamber_pressure=20, of_ratio=6.0,
                                   fuel_type='aluminum')
            r = m.calculate()
        b = r['oxidizer_inlet_state']
        assert b['chamber_temperature_source'] != 'equilibrium'
        assert b['entered_equilibrium'] is False
        assert 'note' in b and 'did not enter' in b['note']


#: V301/B7 — gaz + C(gr) kâhininin O/F 1,0 / 30 bar değeri [K] (aşağıdaki
#: bağımsız kâhinle ölçüldü, 21 Eki 2026). Gaz-yalnız eski değer
#: 1094,966551526537 K idi.
KAHIN_OF1_GAZ_CGR_K = 1420.232512836792


class TestCanteraKahini:
    """HRMA'nın HP kökü ⟷ Cantera'nın DOĞRUDAN dengesi (bağımsız kâhin).

    Reaktan entalpisi ürünün ``oxidizer_inlet`` yolundan DEĞİL, JANAF gaz
    değeri + CoolProp'un düşük yoğunluk limitinden kurulur; denge sıcaklığı
    Cantera ``equilibrate('TP')`` + Brent kök aramasıyla bulunur. Bu kâhin
    ``tests/test_combustion.py``deki iki HP çapasının yeni değerini verir.
    """

    # V301/B7 (21 Eki, ÖNEMLİ, Berke onaylı) — O/F 1,0 ÇAPASI YENİLENDİ.
    # O/F 1,0'da gaz dengesi karbonca aşırı doymuş (ln a_C > 0): gerçek
    # denge gaz + katı karbon C(gr)'dir (NASA RP-1311 Part I eş. 2.11, 3.7).
    # Kâhin de buna göre genişletildi ve HRMA'dan BAĞIMSIZ kaldı: karbon
    # aktivitesi μ_CH4 − 2μ_H2 − μ°_C(gr) ile (HRMA en küçük kareler element
    # potansiyeli kullanır), grafit termosu Cantera graphite.yaml türünden,
    # iç kök ε'da brentq. Önce (gaz-yalnız) 1094,966551526537 K → sonra
    # 1420,232512836792 K (HRMA 1420,23145 K, fark 1,1e-3 K). O/F 4,0'te
    # gaz doymamış; kâhin ε = 0 ile eski değeri birebir verir. Kanıt: docs/scofield/raw/OH/V301/makale1/B7/RAPOR.md.
    @pytest.mark.parametrize('of, beklenen', [
        (1.0, KAHIN_OF1_GAZ_CGR_K), (4.0, 2720.0317189114135)])
    def test_hp_koku_cantera_ile_ayni(self, of, beklenen):
        ct = pytest.importorskip('cantera')
        from scipy.optimize import brentq
        ca = _analizci()
        el = ca._calculate_elemental_composition({'htpb': 100.0}, 'n2o', of)
        comp = ','.join(f'{k}:{v:.12g}' for k, v in el.items() if v > 1e-10)
        sp = ca.propellant_specs['htpb']
        h_y = sp['enthalpy_formation'] * 1e6 / sp['molecular_weight']
        h_o = (HF_GAZ + _bagimsiz_duzeltme_kj_mol(293.15)) * 1e6 / (
            ca.propellant_specs['n2o']['molecular_weight'])
        h_t = (h_y + of * h_o) / (1.0 + of)
        gaz = ct.Solution('gri30.yaml')
        gr = [t for t in ct.Species.list_from_file('graphite.yaml')
              if t.name == 'C(gr)'][0].thermo
        M_C = gaz.atomic_weight('C')
        y0 = {k: v for k, v in el.items() if v > 1e-10}
        top = sum(y0.values())
        y0 = {k: v / top for k, v in y0.items()}

        def _gaz_kur(T, e):
            y = dict(y0)
            y['C'] -= e
            gaz.TPY = T, 30e5, {k: v / (1.0 - e) for k, v in y.items()}
            gaz.equilibrate('TP')

        def _ln_aC(T, e):
            _gaz_kur(T, e)
            mu = gaz.chemical_potentials
            lam = mu[gaz.species_index('CH4')] - 2 * mu[gaz.species_index('H2')]
            return (lam - (gr.h(T) - T * gr.s(T))) / (ct.gas_constant * T)

        def _kalan(T):
            e = 0.0
            if _ln_aC(T, 0.0) > 0.0:
                e = brentq(lambda x: _ln_aC(T, x), 0.0, y0['C'] * (1 - 1e-9),
                           xtol=1e-15, rtol=1e-14)
            _gaz_kur(T, e)
            h_s = gr.h(T) / M_C
            return (1.0 - e) * gaz.enthalpy_mass + e * h_s - h_t

        T_kahin = brentq(_kalan, 300.0, 5000.0, xtol=1e-10, rtol=1e-14)
        assert T_kahin == pytest.approx(beklenen, abs=1e-3)
        T_hrma = ca.analyze_combustion({'htpb': 100.0}, 'n2o', of, 30.0)[
            'conditions']['chamber']['T']
        assert T_hrma == pytest.approx(T_kahin, abs=0.05)


# ---------------------------------------------------------------------------
# 2. tur — form bağlantısı (Ş-7) ve UQ fabrikası (Ş-4), karar §28-18
# ---------------------------------------------------------------------------
def _form_govdesi(**ek):
    """D36 örnek hibrit form gövdesi (getFormData çıktısı), hızlı kip."""
    import json
    import os
    yol = os.path.join(os.path.dirname(__file__), 'fixtures',
                       'd36_hibrit_ornek_govde.json')
    with open(yol, encoding='utf-8') as f:
        govde = json.load(f)['govde']
    govde = dict(govde, calculate_trajectory=False, include_plots=False)
    for k, v in ek.items():
        if v is None:
            govde.pop(k, None)
        else:
            govde[k] = v
    return govde


@pytest.fixture(scope='module')
def _istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(uc, json=govde,
                         headers={'X-Requested-With': 'XMLHttpRequest'})
    return r.status_code, (r.get_json(silent=True) or {})


class TestFormBaglantisi:
    """Formdaki ``oxidizer_phase`` ve tank sıcaklığı YANMAYA ulaşır.

    1. turda faz yalnız InjectorDesign'a gidiyordu (``app.py`` /calculate);
    'gas' seçen kullanıcı sıvı entalpisiyle yakılıyordu (denetim V8:
    T_c 3389,1 → 3333,0 K). Sıvı ve gaz yolu AYRI sınanır (Astra şartı).
    Ters mutasyon (/calculate kurucusundan ``oxidizer_phase`` çıkarılır)
    gaz bekçisini KIRMIZI yapar: mutasyon.md.
    """

    def test_calculate_gaz_yolu_motorun_gaz_sonucunu_verir(self, _istemci):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        kod, j = _post(_istemci, '/calculate',
                       _form_govdesi(oxidizer_phase='gas'))
        assert kod == 200, j
        beyan = j['motor']['oxidizer_inlet_state']
        assert beyan['phase'] == 'gas'
        assert beyan['inlet_phase_source'] == 'user input (oxidizer_phase)'
        assert beyan['formation_enthalpy_kJ_mol'] == HF_GAZ
        # Formdan gelen gaz sonucu, motorun doğrudan 'gas' kurulumuyla
        # BİT-AYNI (aynı denge, aynı reaktan entalpisi).
        g = _form_govdesi()
        with contextlib.redirect_stdout(io.StringIO()):
            m = HybridRocketEngine(
                thrust=g['thrust'], burn_time=g['burn_time'],
                chamber_pressure=g['chamber_pressure'],
                of_ratio=g['of_ratio'], fuel_type=g['fuel_type'],
                regression_a=g['regression_a'],
                regression_n=g['regression_n'],
                fuel_density=g['fuel_density'],
                tank_temperature=g['oxidizer_temp'], oxidizer_phase='gas')
            m.calculate()
        assert j['motor']['chamber_temperature'] == m.T_c

    def test_calculate_sivi_yolu_ve_273K(self, _istemci):
        kod_s, sivi = _post(_istemci, '/calculate', _form_govdesi())
        kod_g, gaz = _post(_istemci, '/calculate',
                           _form_govdesi(oxidizer_phase='gas'))
        kod_t, soguk = _post(_istemci, '/calculate',
                             _form_govdesi(oxidizer_temp=273.15))
        assert (kod_s, kod_g, kod_t) == (200, 200, 200)
        bs = sivi['motor']['oxidizer_inlet_state']
        bt = soguk['motor']['oxidizer_inlet_state']
        assert bs['phase'] == 'liquid' and bt['phase'] == 'liquid'
        assert bt['temperature_K'] == 273.15
        assert bt['formation_enthalpy_kJ_mol'] == pytest.approx(
            HF_GAZ + _bagimsiz_duzeltme_kj_mol(273.15), abs=1e-6)
        Tc = lambda j: j['motor']['chamber_temperature']  # noqa: E731
        assert Tc(soguk) < Tc(sivi) < Tc(gaz)

    def test_bilinmeyen_faz_formdan_400(self, _istemci):
        kod, j = _post(_istemci, '/calculate',
                       _form_govdesi(oxidizer_phase='vapor'))
        assert kod == 400
        assert 'phase' in str(j.get('error', ''))

    def test_hizli_geometri_fazi_iletir(self, _istemci):
        kod, j = _post(_istemci, '/api/quick-geometry',
                       _form_govdesi(oxidizer_phase='gas'))
        assert kod == 200, j
        assert j['motor']['oxidizer_inlet_state']['phase'] == 'gas'

    def test_optimum_ucu_giris_durumunu_iletir_ve_beyan_eder(self, _istemci):
        temel = {'fuel': 'htpb', 'oxidizer': 'n2o', 'chamber_pressure': 25,
                 'motor_type': 'hybrid'}
        kod_v, v = _post(_istemci, '/api/find-optimum-of', temel)
        kod_g, g = _post(_istemci, '/api/find-optimum-of',
                         dict(temel, oxidizer_phase='gas'))
        assert (kod_v, kod_g) == (200, 200), (v, g)
        assert v['oxidizer_inlet_state']['inlet_state_source'] == 'default'
        assert g['oxidizer_inlet_state']['phase'] == 'gas'
        assert g['oxidizer_inlet_state']['request_applied'] is True
        assert g['max_isp'] > v['max_isp']

    def test_yuzey_ucu_uygulanmayan_istegi_adiyla_soyler(self, _istemci):
        kod, j = _post(_istemci, '/api/advanced-performance-analysis', {
            'analysis_type': '3d_surface', 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'grid_n': 3, 'tank_temperature': 273.15})
        assert kod == 200, j
        b = j['oxidizer_inlet_state']
        assert b['request_applied'] is False
        assert b['inlet_state_source'] == 'default'
        assert b['requested_temperature'] == 273.15


#: Yanma grafiğindeki O/F taraması izlerinin adları
#: (hrma/visualization/visualization.py create_combustion_analysis_plots).
OF_TARAMA_IZI = 'Isp vs O/F'
OF_TARAMA_AZAMI_IZI = 'Sweep maximum'

#: Geçici analiz bekçisinin gövdesi (küçük motor; yüklü makinede ~5 s/istek).
#: Anahtarlar HybridRocketEngine kurucu adlarıyla aynı (doğrudan yol için).
GECICI_GOVDE = {'thrust': 1000.0, 'burn_time': 3.0, 'of_ratio': 6.0,
                'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                'oxidizer_type': 'n2o'}
#: Fazın izini taşıyan geçici yanıt yaprakları (sıvı/gaz farkı ölçüldü).
GECICI_SAYISAL_YAPRAKLAR = ('thrust', 'mdot_fuel', 'chamber_pressure',
                            'average_thrust', 'total_impulse')


def _plot_izleri(plot):
    """Plotly JSON'undan ad → iz sözlüğü."""
    import json
    p = json.loads(plot) if isinstance(plot, str) else plot
    return {iz.get('name'): iz for iz in p.get('data', [])}


def _gaz_analizorlu_tarama(govde, of_noktalari):
    """'gas' durumuna ayarlanmış BAĞIMSIZ analizörle O/F taraması.

    /calculate'in grafik yolunu tekrarlamaz; her O/F noktasında denge
    doğrudan çözülür (``performance.isp``).
    """
    a = _analizci()
    a.set_oxidizer_inlet_state(None, 'gas')
    yakit = {govde['fuel_type']: 100.0}
    of_l, isp_l = [], []
    with contextlib.redirect_stdout(io.StringIO()):
        for of in of_noktalari:
            r = a.analyze_combustion(dict(yakit), govde['oxidizer_type'],
                                     float(of),
                                     float(govde['chamber_pressure']))
            of_l.append(float(of))
            isp_l.append(float(r['performance']['isp']))
    return of_l, isp_l


class TestYanUclar:
    """Ş-7: bağımsız analizör ve parametrik uçlar giriş durumunu iletir."""

    def test_ileri_analiz_yanma_kolu_giris_durumunu_iletir(self, _istemci):
        temel = {'analysis_types': ['combustion'],
                 'motor_data': {'chamber_pressure': 25, 'of_ratio': 6.0,
                                'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}}
        kod_v, v = _post(_istemci, '/api/advanced-analysis', temel)
        kod_t, t = _post(_istemci, '/api/advanced-analysis',
                         dict(temel, oxidizer_temp=273.15))
        kod_c, c = _post(_istemci, '/api/advanced-analysis',
                         dict(temel, oxidizer_temp=273.15,
                              motor_data=dict(temel['motor_data'],
                                              oxidizer_temp=283.15)))
        assert (kod_v, kod_t, kod_c) == (200, 200, 422), (v, t, c)
        bv = v['results']['oxidizer_inlet_state']
        bt = t['results']['oxidizer_inlet_state']
        assert bv['inlet_state_source'] == 'default'
        assert bt['temperature_K'] == 273.15 and bt['request_applied'] is True
        Tc = lambda j: (j['results']['combustion_analysis']['compositions']  # noqa: E731
                        ['chamber']['temperature'])
        assert Tc(t) < Tc(v)

    def test_parametrik_tarama_giris_durumunu_iletir(self, _istemci):
        temel = {'thrust': 1000, 'burn_time': 5, 'of_ratio': 6.0,
                 'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                 'param_type': 'chamber_pressure', 'param_start': 20.0,
                 'param_end': 25.0, 'param_steps': 2}
        kod_g, g = _post(_istemci, '/parametric-analysis',
                         dict(temel, oxidizer_phase='gas'))
        kod_s, s = _post(_istemci, '/parametric-analysis', temel)
        kod_r, r = _post(_istemci, '/parametric-analysis',
                         dict(temel, oxidizer_temp=320.0))
        assert (kod_g, kod_s, kod_r) == (200, 200, 400), (g, s, r)
        assert g['oxidizer_inlet_state']['phase'] == 'gas'
        assert s['oxidizer_inlet_state']['phase'] == 'liquid'
        assert g['results'][0]['isp'] > s['results'][0]['isp']
        assert r['error'] == 'invalid_oxidizer_inlet_state'

    def test_calculate_yanma_grafigi_motorun_giris_durumunu_kullanir(
            self, _istemci):
        """Grafik analizörü ve O/F taraması motorla aynı durumda.

        Ölçüldü (sart2a-p1a/form_kiyas): 1. turda yanma grafiği girişten
        bağımsız tek bir JSON'du (sıvı/gaz/273 K bayt-aynı).
        """
        ek = dict(include_plots=True)
        _, sivi = _post(_istemci, '/calculate', _form_govdesi(**ek))
        _, gaz = _post(_istemci, '/calculate',
                       _form_govdesi(oxidizer_phase='gas', **ek))
        gs, gg = (sivi['plots']['combustion_analysis'],
                  gaz['plots']['combustion_analysis'])
        assert gs and gg and gs != gg
        # 3. tur Ş-2: grafik BÜTÜNÜNÜN farklı olması yetmez — bileşim ve
        # istasyon sıcaklığı izleri doğru olup O/F taraması yanlış giriş
        # durumunda çözülse de gs != gg tutuyordu (denetçi D7 mutasyonu
        # yeşil kaldı). Tarama izi AYRICA sınanır: 'gas' izi sıvıdan farklı
        # ve 'gas' durumuna ayarlanmış bağımsız bir analizörün taramasıyla
        # BİT-AYNI.
        iz_s, iz_g = _plot_izleri(gs), _plot_izleri(gg)
        for ad in (OF_TARAMA_IZI, OF_TARAMA_AZAMI_IZI):
            assert iz_g[ad]['y'] and iz_g[ad]['y'] != iz_s[ad]['y'], ad
        beklenen_of, beklenen_isp = _gaz_analizorlu_tarama(
            _form_govdesi(), iz_g[OF_TARAMA_IZI]['x'])
        assert list(iz_g[OF_TARAMA_IZI]['x']) == beklenen_of
        assert list(iz_g[OF_TARAMA_IZI]['y']) == beklenen_isp
        k = beklenen_isp.index(max(beklenen_isp))
        assert list(iz_g[OF_TARAMA_AZAMI_IZI]['y']) == [beklenen_isp[k]]

    def test_gecici_analiz_giris_fazini_iletir(self, _istemci):
        """3. tur Ş-1: /api/transient-analysis fazı motora iletir.

        2. turda bağlantı yapıldı (app.py transient kurucusu
        ``oxidizer_phase``) ama bekçisi yoktu: denetçinin D1 mutasyonu
        (satır silindi) hiçbir testi kırmızı yapmadı. 'gas' ve fazsız
        (varsayılan sıvı) istek AYNI gövdeyle; gaz yanıtı, doğrudan
        ``HybridRocketEngine(oxidizer_phase='gas')`` + ``TransientBallistics``
        yolunun çıktısıyla BİT-AYNI olmalı.
        """
        from hrma.analysis.transient_ballistics import TransientBallistics
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        kod_g, g = _post(_istemci, '/api/transient-analysis',
                         dict(GECICI_GOVDE, oxidizer_phase='gas'))
        kod_s, s = _post(_istemci, '/api/transient-analysis', GECICI_GOVDE)
        assert (kod_g, kod_s) == (200, 200), (g, s)
        assert g['oxidizer_inlet_state']['phase'] == 'gas'
        assert s['oxidizer_inlet_state']['phase'] == 'liquid'
        tg, ts = g['transient'], s['transient']
        for ad in GECICI_SAYISAL_YAPRAKLAR:
            assert tg[ad] != ts[ad], ad
        with contextlib.redirect_stdout(io.StringIO()):
            m = HybridRocketEngine(oxidizer_phase='gas', **GECICI_GOVDE)
            m.calculate()
            dogrudan = TransientBallistics(m).solve()
        for ad in GECICI_SAYISAL_YAPRAKLAR:
            d = dogrudan[ad]
            d = d.tolist() if hasattr(d, 'tolist') else d
            assert tg[ad] == d, ad


class TestUqFabrikasi:
    """Ş-4: /api/uncertainty-analysis nominali /calculate'in giriş durumuyla.

    1. turda fabrika kurucusu tank sıcaklığını ve fazı GEÇİRMİYORDU; UQ
    nominali üç girişte de bit-aynıydı. Ters mutasyon: mutasyon.md.
    """

    @staticmethod
    def _nominal(**ek):
        from hrma.analysis.uq_adapters import make_hybrid_factory
        g = _form_govdesi()
        temel = {k: g[k] for k in ('thrust', 'burn_time', 'of_ratio',
                                   'chamber_pressure', 'fuel_type',
                                   'regression_a', 'regression_n',
                                   'fuel_density')}
        with contextlib.redirect_stdout(io.StringIO()):
            return make_hybrid_factory(dict(temel, **ek))({})

    def test_uq_nominali_motorla_ayni_giris_durumunu_kullanir(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        g = _form_govdesi()
        v = self._nominal()
        t = self._nominal(oxidizer_temp=273.15)
        k = self._nominal(tank_temperature=273.15)
        gaz = self._nominal(oxidizer_phase='gas')
        assert t == k  # takma ad ile kanonik ad aynı
        assert t['c_star'] < v['c_star'] < gaz['c_star']
        with contextlib.redirect_stdout(io.StringIO()):
            m = HybridRocketEngine(
                thrust=g['thrust'], burn_time=g['burn_time'],
                chamber_pressure=g['chamber_pressure'],
                of_ratio=g['of_ratio'], fuel_type=g['fuel_type'],
                regression_a=g['regression_a'],
                regression_n=g['regression_n'],
                fuel_density=g['fuel_density'], tank_temperature=273.15)
            r = m.calculate()
        assert t['c_star'] == r['c_star']
        assert t['isp'] == r['isp']

    def test_uq_gecersiz_giris_adiyla_reddedilir(self):
        with pytest.raises(ValueError, match='saturated-liquid envelope'):
            self._nominal(oxidizer_temp=315.0)


#: UQ yanıt bekçisinin hızlı koşum seçimi (deponun sağlıklı gövdeleri de
#: küçük örnek sayısını bilerek kullanır: test_d28_app_api_a1 n_samples 2).
UQ_BEKCI_ORNEK = 2
UQ_BEKCI_TOHUM = 11


class TestUqYanitBeyani:
    """3. tur Ş-6: /api/uncertainty-analysis yanıtı giriş durumunu beyan eder.

    2. tur yeniden denetimi (8 Eki) ölçtü: UQ yanıtında
    ``oxidizer_inlet_state`` yaprağı yoktu, formül sayfası ise her hibrit
    sonucun beyan taşıdığını söylüyordu. Beyanın sayıları /calculate'teki
    motor beyanıyla AYNI olmalı (tek kaynak). Ters mutasyon: mutasyon.md.
    """

    @staticmethod
    def _uq(istemci, **ek):
        g = _form_govdesi()
        girdi = {k: g[k] for k in ('thrust', 'burn_time', 'of_ratio',
                                   'chamber_pressure', 'fuel_type',
                                   'oxidizer_type', 'regression_a',
                                   'regression_n', 'fuel_density')}
        girdi.update(ek)
        return _post(istemci, '/api/uncertainty-analysis', {
            'motor_type': 'hybrid', 'level': 'fast',
            'seed': UQ_BEKCI_TOHUM, 'n_samples': UQ_BEKCI_ORNEK,
            'inputs': girdi})

    @pytest.mark.parametrize('ek, faz, T', [
        ({}, 'liquid', None),
        ({'oxidizer_temp': 273.15}, 'liquid', 273.15),
        ({'oxidizer_phase': 'gas'}, 'gas', None),
    ])
    def test_uq_yaniti_motorla_ayni_giris_durumunu_beyan_eder(
            self, _istemci, ek, faz, T):
        kod, j = self._uq(_istemci, **ek)
        assert kod == 200, j
        b = j['oxidizer_inlet_state']
        assert b['phase'] == faz
        assert 'temperature_K' in b
        if T is not None:
            assert b['temperature_K'] == T
        # /calculate motor beyanıyla aynı sayılar (fazsız gövde = sıvı).
        _, c = _post(_istemci, '/calculate', _form_govdesi(
            oxidizer_phase=ek.get('oxidizer_phase'),
            oxidizer_temp=ek.get('oxidizer_temp')))
        m = c['motor']['oxidizer_inlet_state']
        for alan in ('phase', 'temperature_K', 'formation_enthalpy_kJ_mol',
                     'enthalpy_correction_kJ_mol'):
            assert b[alan] == m[alan], alan

    def test_uq_lox_beyani_motorla_ayni_sabit_referans(self, _istemci):
        """4. tur Ş-2 (b): LOX hibrit UQ'su N₂O beyanı UYDURMAZ.

        Yeniden denetim-3'ün E5 mutasyonu (``_uq_hybrid_inlet_state_
        declaration``'da oksitleyici okunmaz) LOX UQ'sunu 'N₂O doymuş sıvı'
        beyanına çeviriyordu ve parametreli bekçi yeşil kalıyordu (LOX vakası
        yoktu). Beyanın kimlik alanları /calculate motor beyanıyla ``==``.
        """
        kod, j = self._uq(_istemci, oxidizer_type='lox')
        assert kod == 200, j
        b = j['oxidizer_inlet_state']
        _, c = _post(_istemci, '/calculate', _form_govdesi(
            oxidizer_type='lox', oxidizer_phase=None, oxidizer_temp=None))
        m = c['motor']['oxidizer_inlet_state']
        for alan in ('oxidizer', 'phase', 'status'):
            assert b[alan] == m[alan], alan
        assert (b['oxidizer'], b['phase'], b['status']) == (
            'lox', 'liquid', 'fixed_reference')
        assert b['temperature_applied'] is False
        # N₂O giriş durumunun sayıları LOX beyanında yer almaz.
        for alan in ('temperature_K', 'formation_enthalpy_kJ_mol',
                     'enthalpy_correction_kJ_mol'):
            assert alan not in b, alan
            assert alan not in m, alan


class TestSonucPaneliGirisSatiri:
    """3. tur Ş-5 (karar §28-18 "açık varsayım olarak beyan"): hibrit sonuç
    panelinde N₂O giriş durumu TEK SATIR (app.js ``defaultsAppliedBlock``).

    Satır motorun beyanından okunur; beyan değişirse satır değişir, beyan
    yoksa satır yoktur. Sözlük EN = TR. Ters mutasyon: mutasyon.md.
    node koşum takımı ``tests/test_d37_hibrit_a1.py``ninkidir (ikinci kopya
    yazılmaz).
    """

    @staticmethod
    def _satir(yanit, dil):
        import re
        from tests.test_d37_hibrit_a1 import _node, _metin
        html = _node({'sozluk': True, 'dil': dil,
                      'defaults_results': yanit})['defaults_html']
        m = re.search(r'<div class="hd-oxidizer-inlet-line".*?</div>', html,
                      re.S)
        return (_metin(m.group(0)) if m else None), html

    @pytest.fixture(scope='class')
    def _yanitlar(self, _istemci):
        kod_v, v = _post(_istemci, '/calculate', _form_govdesi(
            oxidizer_phase=None, oxidizer_temp=None))
        kod_g, g = _post(_istemci, '/calculate', _form_govdesi(
            oxidizer_phase='gas'))
        assert (kod_v, kod_g) == (200, 200), (v, g)
        return v, g

    def test_varsayilan_ve_gaz_satiri_motor_beyanindan(self, _yanitlar):
        from tests.test_d37_hibrit_a1 import NODE
        if NODE is None:
            pytest.skip('node kurulu değil')
        v, g = _yanitlar
        assert v['motor']['oxidizer_inlet_state']['temperature_K'] == 293.15
        tr, _ = self._satir(v, 'tr')
        en, _ = self._satir(v, 'en')
        assert tr == ('N₂O giriş: 293,15 K doymuş sıvı '
                      '(varsayım; RP-1311 §4.1)'), tr
        assert en == ('N₂O inlet: 293.15 K saturated liquid '
                      '(assumption; RP-1311 §4.1)'), en
        gtr, _ = self._satir(g, 'tr')
        assert gtr == 'N₂O giriş: 298,15 K ideal gaz, standart hâl (girdiniz)'

    def test_satir_beyani_okur_ve_beyansiz_satir_yok(self, _yanitlar):
        import copy
        from tests.test_d37_hibrit_a1 import NODE
        if NODE is None:
            pytest.skip('node kurulu değil')
        v, _ = _yanitlar
        # Beyan değişince satır AYNI değeri basar (sabit yazılmamış).
        y = copy.deepcopy(v)
        b = y['motor']['oxidizer_inlet_state']
        b['temperature_K'] = 281.37
        b['inlet_temperature_source'] = 'user input (tank_temperature)'
        tr, _ = self._satir(y, 'tr')
        assert tr == ('N₂O giriş: 281,37 K doymuş sıvı (sıcaklık: girdiniz; '
                      'faz: varsayım; RP-1311 §4.1)'), tr
        # Beyan yoksa satır HİÇ yok; künye bloğu etkilenmez.
        y2 = copy.deepcopy(v)
        del y2['motor']['oxidizer_inlet_state']
        tr2, html2 = self._satir(y2, 'tr')
        _, html1 = self._satir(v, 'tr')
        assert tr2 is None
        assert html1.endswith(html2)

    def test_kunye_listesi_bosken_satir_yine_cizilir(self, _yanitlar):
        """4. tur Ş-2 (a): ``defaults_applied`` boşken N₂O satırı düşmez.

        Yeniden denetim-3'ün E4 mutasyonu (künye listesi boşsa erken
        ``return ''``) satırı sessizce siliyordu; fikstür yanıtlarında liste
        hep dolu olduğu için bekçiler yeşil kalıyordu. Bütün alanları dolu
        gönderilen bir hibrit koşunun yanıtı bu biçimdedir.
        """
        import copy
        from tests.test_d37_hibrit_a1 import NODE
        if NODE is None:
            pytest.skip('node kurulu değil')
        v, _ = _yanitlar
        assert v['defaults_applied']  # gerçek yanıtta liste dolu
        y = copy.deepcopy(v)
        y['defaults_applied'] = []
        # Dolu listeli satırın metni beyandan okunduğu ve sabitlendiği yer:
        # test_varsayilan_ve_gaz_satiri_motor_beyanindan (ikinci kopya yok).
        for dil in ('tr', 'en'):
            dolu, html_dolu = self._satir(v, dil)
            bos, html = self._satir(y, dil)
            assert dolu is not None and 'hd-defaults-applied-row' in html_dolu
            assert bos == dolu, (dil, bos, dolu)
            assert 'hd-defaults-applied-row' not in html

    def test_sozluk_en_tr_esit(self):
        import pathlib
        import re
        kaynak = (pathlib.Path(__file__).resolve().parents[1] / 'hrma' /
                  'static' / 'js' / 'i18n_common.js').read_text('utf-8')
        tr_bas = kaynak.index('\n        tr: {')
        en = set(re.findall(r"'(app\.oxInlet\.\w+)'", kaynak[:tr_bas]))
        tr = set(re.findall(r"'(app\.oxInlet\.\w+)'", kaynak[tr_bas:]))
        assert en and en == tr, (en ^ tr)
