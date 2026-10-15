# -*- coding: utf-8 -*-
"""ÖH Dalga-29 · kulvar ``app-api-uc`` · aşama 3/3 — P07 uç ailesi bekçisi.

Her sınıf TEK bir defter kalemine bağlıdır ve o kalemin ÖLÇÜLEN kusurunu
görür. Ölçümler ``docs/scofield/raw/OH/D29/app-api-uc/a3/once.json`` ve
``sonra.json`` dosyalarındadır; ters-mutasyon kanıtı ``mutasyon.json``.

Kapsanan kalemler:
  P7B1-22  /api/analysis/thermal-protection tüketicisiz takma yol
  P7B1-23  /api/gimbal-mount cıvata çifti (künye ⟷ koşul çaprazı)
  P7B2-12  /api/combustion-stability besleme hattı işaret kaybı
  P7B2-13  /api/regen-cooling iletilmeyen kurucu parametreleri
  P7B2-20  _ThreadLocalLineDedup akış sözleşmesi
  P7B2-21  /parametric-analysis tekil analizör sızıntısı (ÇÜRÜTÜLDÜ)
  P7B2-22  /parametric-analysis param_start/param_end kapısı (ÇÜRÜTÜLDÜ)
  P7B2-23  /api/slosh-analysis iki hata dili
  P7B3-11  molecular_weight aynı anahtar iki tip
  P7B3-33  /api/fea/planar-grain üst basınç kapısı
  P7B4-07  /api/flow-analysis kesirli n_stations sessiz kırpma
"""
import contextlib
import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
APP_PY = KOK / 'hrma' / 'app.py'


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def gonder(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=govde)
    return r.status_code, (r.get_json() or {}), r.get_data()


# ===========================================================================
# P7B1-22 — /api/analysis/thermal-protection: tüketicisiz kamu yolu
# ===========================================================================
class TestP7B122OluTakmaYol:
    """ÖLÇÜLDÜ (``a3/once.json`` K1): takma yol ile birincil yol BİT-AYNI
    yanıt veriyor (``sha256 6eb7419eee63d17d``, 1691 bayt), ama ürün yüzünde
    takma yola giden **0** dosya var; birincil yola **2**
    (``analysis_dock.js``, ``panels/protection_panel.js``). Kardeş takma yol
    ``/api/analysis/combustion-stability`` ise CANLI (2 dosya:
    ``analysis_center.js``, ``panels/stability_panel.js``) — yani
    ``/api/analysis/*`` uzayı topluca ölü değil, ölü olan BU yapraktır.

    ÖH D30 / app-api-uc a1: YOL SİLİNDİ (OH-D29-13). Aşağıdaki ölçütler
    yürürlükte kalır (silmenin gerekçesini kilitlerler); yalnız bit-aynılık
    bekçisi kaldırma bekçisine çevrildi.

    (D29 kaydı) Yolun SİLİNMESİ o aşamada yapılamadı: POST eden tüketicileri
    ``tests/support/uc_katalogu.py``, ``tests/support/uc_yukleri.json`` ve
    ``tests/test_d15_termo_ucus_a3.py`` dosyalarındadır (bekci-cevirisi /
    termo-ucus sahası; termo-ucus D29'da PARALEL koşuyor). Bu dosya ölçümü
    KİLİTLER, böylece kayıt çürümez ve silme kararı ölçülmüş bir zemine
    dayanır.
    """

    URUN = ('hrma/static', 'hrma/templates', 'electron')

    @staticmethod
    def _urun_tuketicileri(desen):
        bulunan = []
        for d in TestP7B122OluTakmaYol.URUN:
            p = KOK / d
            if not p.is_dir():
                continue
            out = subprocess.run(['grep', '-rl', desen, str(p)],
                                 capture_output=True, text=True).stdout
            bulunan += [x for x in out.split('\n') if x]
        return sorted(set(bulunan))

    def test_takma_yolun_urun_tuketicisi_yok(self):
        assert self._urun_tuketicileri('analysis/thermal-protection') == []

    def test_birincil_yolun_urun_tuketicisi_var(self):
        """Kusur "uç ölü" değil "TAKMA yol ölü": birincil canlı kalmalı."""
        assert len(self._urun_tuketicileri('api/thermal-protection')) >= 2

    def test_kardes_takma_yol_canli(self):
        """Ölçütün ayırt edici olduğunun kanıtı: aynı tarama canlı bir takma
        yolu CANLI buluyor. Tarama her şeye "ölü" demiyor."""
        assert len(
            self._urun_tuketicileri('analysis/combustion-stability')) >= 2

    def test_d24_gerekcesinin_dosya_atfi_yanlis(self):
        """OH-D23-12'nin ANDIĞI dosyada ilgili dizge yok.

        ÖNEMLİ AYRIM (ölçüldü, bu aşamada): D24 envanteri
        (``tests/test_d18_bekci_cevirisi_a1.py``) takma yolu borç
        listesinden çıkarırken YÖNTEM olarak haklıdır — o tarayıcı
        bilerek GÖRÜNÜM FONKSİYONU düzeyinde sayar
        (``_takim_genislet``: "Ürün alias'lardan BİRİNİ çağırıyorsa uç
        çağrılmıştır") ve bu ucun görünümünü ürün gerçekten çağırıyor.
        Yanlış olan yalnız gerekçenin ANDIĞI DOSYADIR: ``thermal_panel.js``
        içinde ``thermal-protection`` dizgesi HİÇ geçmez; çağrıyı yapan
        ``protection_panel.js`` ve ``analysis_dock.js``tir, ikisi de
        BİRİNCİL yolu kullanır.

        Bu yüzden envanter satırı GERİ KONMADI (denendi ve
        ``TestP13B208UcPanelEnvanteri::test_envanter_curumez`` kırmızıya
        döndü — envanterin kendi ölçütüyle çelişiyor); YOL DÜZEYİNDEKİ
        gerçek bu dosyada kayıt altına alınır.
        """
        panel = KOK / 'hrma' / 'static' / 'js' / 'panels' / 'thermal_panel.js'
        assert panel.is_file(), 'gerekçenin dayandığı dosya kayıp'
        assert 'thermal-protection' not in panel.read_text(encoding='utf-8')

    def test_envanterin_gorunum_duzeyi_olcutu_korunur(self):
        """İki ölçüt bir arada durur; hiçbiri ötekini bastırmaz.

        Envanter GÖRÜNÜM düzeyinde sayar (ve bu yüzden takma yolu borç
        saymaz); bu dosya YOL düzeyinde sayar (ve takma yolun tüketicisiz
        olduğunu kilitler). Envanterin ölçütü sessizce değişirse burası
        haber verir.
        """
        envanter = (KOK / 'tests' / 'test_d18_bekci_cevirisi_a1.py').read_text(
            encoding='utf-8')
        assert '_takim_genislet' in envanter
        assert "alias kardeşi" in envanter
        # Takma yol envanterde borç olarak YAZILI DEĞİL (görünüm ölçütü).
        assert "'/api/analysis/thermal-protection'," not in envanter

    def test_takma_yol_kaldirildi(self, istemci):
        """ÇEVRİLDİ — ÖH D30 / app-api-uc a1 (OH-D29-13 + P7B1-22).

        Eski hâli (``test_iki_yol_hala_bit_ayni``) iki yolun BİT-AYNI yanıt
        vermesini şart koşuyordu ve gerekçesi açıkça geçiciydi: *"Kaldırma
        kararı verilene kadar"*. Karar D30'da verildi ve takma yol silindi
        (ölçüldü ``D30/app-api-uc/a1/once.json`` K9: ürün tarafında 0
        eşleşme; tüketiciler yalnız deponun kendi envanteriydi ve aynı
        commit'te güncellendi). Bekçi artık kaldırmayı KİLİTLER: takma yol
        404 döner, birincil yol çalışmayı sürdürür — yani kusur "uç
        emekliye ayrıldı" diye geri sızamaz.
        """
        yuk = {'mode': 'ablative', 'q_net_W_m2': 1e6, 'burn_time_s': 10,
               'material': 'carbon_phenolic', 'q_star_MJ_kg': 5.0}
        birincil = istemci.post('/api/thermal-protection', json=yuk)
        assert birincil.status_code == 200, birincil.status_code
        takma = istemci.post('/api/analysis/thermal-protection', json=yuk)
        assert takma.status_code == 404, takma.status_code


# ===========================================================================
# P7B1-23 — /api/gimbal-mount cıvata çifti
# ===========================================================================
GIMBAL = {'thrust_N': 1.0e6, 'gimbal_angle_deg': 6.0, 'actuator_arm_m': 0.5,
          'ring_offset_m': 0.4, 'thrust_offset_m': 0.01}


class TestP7B123CivataCifti:
    """ÖLÇÜLDÜ (``a3/once.json`` K2): künye "3'ten az cıvata -> 400" diyor,
    kural KOŞULLUYDU. ``bolt_count=2`` + ``bolt_circle_diameter_m=0,6``
    -> 400 (doğru); ``bolt_count=2`` tek başına -> **HTTP 200** ve yanıtın
    tamamında ``bolt_count`` dizgesi **0 kez** geçiyordu. ``bolt_count=0``
    tek başına da 200. Gönderilen girdi ne kullanılıyor ne reddediliyor ne
    beyan ediliyordu.
    """

    def test_yalniz_bolt_count_422(self, istemci):
        kod, j, _ = gonder(istemci, '/api/gimbal-mount',
                           dict(GIMBAL, bolt_count=0))
        assert kod == 422, (kod, j)
        assert j['error'] == 'incomplete_bolt_pattern_input'
        assert j['missing_fields'] == ['bolt_circle_diameter_m']
        assert j['invalid_fields'][0]['field'] == 'bolt_count'
        assert j['invalid_fields'][0]['reason'] == 'missing_companion_field'

    def test_yalniz_cap_422(self, istemci):
        kod, j, _ = gonder(istemci, '/api/gimbal-mount',
                           dict(GIMBAL, bolt_circle_diameter_m=0.6))
        assert kod == 422, (kod, j)
        assert j['missing_fields'] == ['bolt_count']

    def test_gecersiz_sayi_artik_sessizce_dusmuyor(self, istemci):
        """Ölçülen kusurun tam ikizi: 2 cıvata, çap yok."""
        kod, j, ham = gonder(istemci, '/api/gimbal-mount',
                             dict(GIMBAL, bolt_count=2))
        assert kod == 422, kod
        # gonderilen deger yanitta ADIYLA gecer (once 0 kez geciyordu)
        assert ham.decode('utf-8').count('bolt_count') >= 1
        assert j['invalid_fields'][0]['submitted'] == 2

    def test_cift_kuruluysa_modul_hukmu_aynen_kosar(self, istemci):
        """Kapı modülün kendi kapısını GÖLGELEMEZ: 400 hükmü korunur."""
        kod, j, _ = gonder(
            istemci, '/api/gimbal-mount',
            dict(GIMBAL, bolt_count=2, bolt_circle_diameter_m=0.6))
        assert kod == 400, (kod, j)
        assert 'minimum 3' in str(j.get('error'))

    def test_saglikli_govde_bit_ayni(self, istemci):
        """ÖK-22: sağlıklı envanter gevşemez de daralmaz da."""
        kod, j, _ = gonder(
            istemci, '/api/gimbal-mount',
            dict(GIMBAL, bolt_count=12, bolt_circle_diameter_m=0.6))
        assert kod == 200, kod
        assert j['bolts']['bolt_count'] == 12

    def test_hicbiri_verilmezse_davranis_korunur(self, istemci):
        """Kullanicinin hic sormadigi cıvata zinciri icin bir sey duşmez:
        yanit TABAN AGACIYLA bayt-ayni (``a3/once.json`` K2
        ``bcd_yok_bolt_yok``: sha256 344aa7d215bafceb, 6732 bayt)."""
        kod, j, ham = gonder(istemci, '/api/gimbal-mount', dict(GIMBAL))
        assert kod == 200, kod
        assert j.get('bolts') is None
        assert len(ham) == 6732
        assert hashlib.sha256(ham).hexdigest()[:16] == '344aa7d215bafceb'

    def test_kunye_kosulu_soyluyor(self):
        from hrma.app import app
        doc = app.view_functions['gimbal_mount_analysis'].__doc__ or ''
        assert 'CIVATA ÇİFTİ' in doc
        assert 'bolt_circle_diameter_m' in doc


# ===========================================================================
# P7B2-12 — /api/combustion-stability besleme hattı işaret kaybı
# ===========================================================================
CS = {'mode': 'chug', 'dp_ratio_j': 0.3, 'tau_s': 0.002, 'tau_c_s': 0.003}
FEED = {'length_m': 1.5, 'mass_flow_kg_s': 2.0, 'dp_injector_Pa': 5.0e5}


class TestP7B212BeslemeHattiIsareti:
    """ÖLÇÜLDÜ (``a3/once.json`` K3): ``diameter_mm = -12`` HTTP **200** ve
    yanıt ``line_diameter_mm = -12,0`` ile ``line_area_m2 = +1,1310e-4``
    alanlarını yan yana yayımlıyordu. Aynı çekirdek kapısı ``area_m2 =
    -1,13e-4`` ile doğrudan çağrıldığında 400 veriyordu — kapı VARDI,
    uçtaki A = pi*d^2/4 çevirisi işareti yok ettiği için ulaşılamıyordu.
    """

    def test_negatif_cap_reddedilir(self, istemci):
        kod, j, _ = gonder(istemci, '/api/combustion-stability',
                           dict(CS, feed_line=dict(FEED, diameter_mm=-12.0)))
        assert kod == 400, (kod, j)
        assert 'feed_line.diameter_mm' in str(j.get('error'))
        assert '-12' in str(j.get('error'))

    def test_pozitif_alan_yayimlanmaz(self, istemci):
        """Kusurun imzası: negatif çapın yanında POZİTİF alan."""
        _, j, ham = gonder(
            istemci, '/api/combustion-stability',
            dict(CS, feed_line=dict(FEED, diameter_mm=-12.0)))
        assert 'line_area_m2' not in ham.decode('utf-8')

    def test_sifir_cap_reddedilir(self, istemci):
        kod, j, _ = gonder(istemci, '/api/combustion-stability',
                           dict(CS, feed_line=dict(FEED, diameter_mm=0.0)))
        assert kod == 400, kod
        assert 'feed_line.diameter_mm' in str(j.get('error'))

    def test_cekirdek_kapisi_bozulmadi(self, istemci):
        """Doğrudan ``area_m2`` kolu ÖNCEKİ hükmünü aynen verir."""
        kod, j, _ = gonder(istemci, '/api/combustion-stability',
                           dict(CS, feed_line=dict(FEED, area_m2=-1.13e-4)))
        assert kod == 400, kod
        assert 'line_area_m2' in str(j.get('error'))

    def test_saglikli_cap_bit_ayni(self, istemci):
        kod, j, _ = gonder(istemci, '/api/combustion-stability',
                           dict(CS, feed_line=dict(FEED, diameter_mm=12.0)))
        assert kod == 200, kod
        metin = json.dumps(j)
        assert '"line_diameter_mm": 12.0' in metin
        m = re.search(r'"line_area_m2":\s*([-\d.eE+]+)', metin)
        assert m and abs(float(m.group(1)) - 1.1309733552923255e-4) < 1e-18


# ===========================================================================
# P7B2-13 — /api/regen-cooling iletilmeyen kurucu parametreleri
# ===========================================================================
#: Kanatçık modeli YALNIZ süperkritik kolda etkindir (``regen_cooling.py``:
#: ``if sc_mode and self.fin_effect``), bu yüzden ölçüm metan/80 bar ile
#: yapılır — su/rp1 tabanında ``fin_effect`` yanıtı değiştirmez ve bu
#: DOĞRUDUR (modelin kendi kapsamı), bağlanmamışlık değildir.
REGEN_SC = {'chamber_pressure': 50.0, 'chamber_temperature': 3400.0,
            'throat_diameter': 0.05, 'expansion_ratio': 8.0, 'gamma': 1.2,
            'molecular_weight': 22.0, 'coolant': 'methane',
            'coolant_mdot': 2.0, 'coolant_inlet_temp': 120.0,
            'coolant_inlet_pressure': 80.0, 'n_channels': 80,
            'channel_width': 2.0, 'channel_height': 3.0,
            'wall_thickness': 1.0, 'wall_material': 'cucrzr'}


class TestP7B213KurucuParametreleri:
    """ÖLÇÜLDÜ (``a3/once.json`` K4): ``inspect.signature`` ⟷ uç gövdesi
    çaprazı, ``RegenCooling.__init__``in 23 parametresinden İKİSİ uçta hiç
    geçmiyordu: ``fin_effect``, ``wall_roughness``. İkisi de gövdeye konsa
    yanıt bit-aynı kalıyordu (``sha256 69e9f20db6ab528f``).
    """

    @staticmethod
    def _ozet(istemci, ek=None):
        gv = dict(REGEN_SC)
        if ek:
            gv.update(ek)
        kod, j, ham = gonder(istemci, '/api/regen-cooling', gv)
        s = ((j.get('cooling') or {}).get('summary') or {})
        return kod, s, ham

    @staticmethod
    def _uc_kod_adlari():
        """``/api/regen-cooling`` gövdesinde KOD olarak geçen adlar.

        Ölçüt (denetim ŞARTI, P7B2-13): yalnız ``kwargs['<ad>'] = ...``
        biçimi anahtar atamaları, çağrı anahtar sözcükleri (``f(ad=...)``)
        ve çıplak tanıtıcılar sayılır. Yorumda ya da hata metninde geçen
        bir ad KOD DEĞİLDİR.
        """
        import ast
        import textwrap
        kaynak = APP_PY.read_text(encoding='utf-8')
        bas = kaynak.index("@app.route('/api/regen-cooling'")
        son = kaynak.index("@app.route('/api/slosh-analysis'", bas)
        govde = textwrap.dedent(kaynak[bas:son])
        adlar = set()
        for d in ast.walk(ast.parse(govde)):
            if (isinstance(d, ast.Subscript)
                    and isinstance(d.slice, ast.Constant)
                    and isinstance(d.slice.value, str)):
                adlar.add(d.slice.value)          # kwargs['wall_roughness']
            elif isinstance(d, ast.keyword) and d.arg:
                adlar.add(d.arg)                  # RegenCooling(fin_effect=...)
            elif isinstance(d, ast.Name):
                adlar.add(d.id)                   # çıplak değişken
        return adlar, govde

    def test_imzadaki_her_parametre_ucta_geciyor(self):
        """İmzadaki her parametre uçta KOD olarak geçer; unutulan kırmızıdır.

        ÖH D33 / P7B2-13 — DENETİM ŞARTI KARŞILANDI (app-api-uc denetçisi,
        15 Eyl). Eski ölçüt metin-üstüydü (``p not in govde``): bir
        parametrenin adının gövdenin HERHANGİ bir yerinde — yorumda, hata
        iletisinde, docstring'de — geçmesi yetiyordu. ÖLÇÜLDÜ (a1/once.json
        P7B2-13, taban 56f88e70): imzadaki 22 parametreden **5'inin adı bir
        yorum satırında da geçiyor** (``coolant``, ``coolant_props_source``,
        ``fin_effect``, ``motor_data``, ``wall_roughness``). Yani bu beşinin
        KOD satırı silinse bile eski ölçüt YEŞİL kalırdı — künyesindeki
        "ikinci bir parametre unutulursa bu test kırmızıya döner" cümlesi
        tam olarak bu beş parametre için yanlıştı.

        Ölçüt artık AST: gövde ayrıştırılır, yalnız ``kwargs['<ad>']``
        anahtar atamaları, çağrı anahtar sözcükleri ve çıplak tanıtıcılar
        sayılır. Künyedeki cümle bugün ölçütle uyumludur.
        """
        import inspect
        from hrma.analysis.regen_cooling import RegenCooling
        kod_adlari, _govde = self._uc_kod_adlari()
        imza = set(inspect.signature(RegenCooling.__init__).parameters)
        imza.discard('self')
        eksik = sorted(p for p in imza if p not in kod_adlari)
        assert eksik == [], (
            'RegenCooling imzasındaki şu parametreler uçta KOD olarak hiç '
            f'geçmiyor: {eksik} (adın yorumda geçmesi yetmez).')

    def test_olcut_yorumdaki_adi_gecis_saymiyor(self):
        """ŞARTIN kendi duyarlılığı: metin-üstü ölçütün körlüğü ölçülür.

        Gövdede yorum satırlarında adı geçen ama kodda geçmeyen bir ad
        uydurulur; eski ölçüt (``ad in govde``) bunu GEÇİŞ sayardı, yeni
        ölçüt (AST) saymaz. Bu, onarımın vakumlanamayacağının kilididir.
        """
        kod_adlari, govde = self._uc_kod_adlari()
        # Gövdenin GERÇEK yorum satırlarında geçen, kodda geçmeyen adlar.
        yorumlar = '\n'.join(s.strip() for s in govde.splitlines()
                             if s.strip().startswith('#'))
        import inspect
        from hrma.analysis.regen_cooling import RegenCooling
        imza = set(inspect.signature(RegenCooling.__init__).parameters)
        imza.discard('self')
        kalkanli = sorted(p for p in imza if p in yorumlar)
        assert kalkanli, (
            'uç gövdesinde artık hiçbir parametre adı yorumda geçmiyor — '
            'bu bekçinin ölçtüğü kör nokta kalmamış olabilir, ölçüm '
            'yenilensin')
        # İki ölçüt SENTETİK bir gövdede yan yana konur: adı YALNIZ
        # yorumda geçen bir parametre eski ölçütü geçer, yenisi geçmez.
        import ast as _ast
        sentetik = ('def uc():\n'
                    '    # wall_roughness burada yalnız ANLATILIYOR\n'
                    "    kwargs = {}\n"
                    "    kwargs['fin_effect'] = True\n"
                    '    return kwargs\n')
        eski_olcut = 'wall_roughness' in sentetik          # metin-üstü
        yeni_adlar = set()
        for d in _ast.walk(_ast.parse(sentetik)):
            if (isinstance(d, _ast.Subscript)
                    and isinstance(d.slice, _ast.Constant)
                    and isinstance(d.slice.value, str)):
                yeni_adlar.add(d.slice.value)
            elif isinstance(d, _ast.keyword) and d.arg:
                yeni_adlar.add(d.arg)
            elif isinstance(d, _ast.Name):
                yeni_adlar.add(d.id)
        assert eski_olcut is True, 'kurgu bozuldu: eski ölçüt geçmeliydi'
        assert 'wall_roughness' not in yeni_adlar, (
            'AST ölçütü YALNIZ yorumda geçen adı kod sayıyor — ŞART '
            'karşılanmamış, ölçüt hâlâ metin-üstü')
        assert 'fin_effect' in yeni_adlar, (
            'AST ölçütü gerçek kwargs anahtarını göremiyor — ölçüt fazla '
            'dar, gerçek geçişler kırmızıya döner')

    def test_fin_effect_yaniti_degistirir(self, istemci):
        kod_a, a, _ = self._ozet(istemci)
        kod_b, b, _ = self._ozet(istemci, {'fin_effect': False})
        assert (kod_a, kod_b) == (200, 200)
        assert a['fin_effect'] is True and b['fin_effect'] is False
        assert a['fin_area_ratio_max'] > 1.0
        assert b['fin_area_ratio_max'] == pytest.approx(1.0)
        assert a['total_pressure_drop_bar'] != b['total_pressure_drop_bar']

    def test_fin_effect_metin_bayragi_kanonik_okunur(self, istemci):
        """``bool('false') == True`` tuzağı (P7B1-20 dersi)."""
        _, b, _ = self._ozet(istemci, {'fin_effect': 'false'})
        assert b['fin_effect'] is False
        kod, j, _ = gonder(istemci, '/api/regen-cooling',
                           dict(REGEN_SC, fin_effect='abc'))
        assert kod == 422, kod

    def test_wall_roughness_yaniti_degistirir(self, istemci):
        kod_a, a, _ = self._ozet(istemci)
        kod_b, b, _ = self._ozet(istemci, {'wall_roughness': 2.0e-4})
        assert (kod_a, kod_b) == (200, 200)
        assert a['total_pressure_drop_bar'] != b['total_pressure_drop_bar']

    def test_wall_roughness_negatif_modul_kapisina_duser(self, istemci):
        kod, j, _ = gonder(istemci, '/api/regen-cooling',
                           dict(REGEN_SC, wall_roughness=-1.0))
        assert kod == 400, kod
        assert 'wall_roughness' in str(j.get('error'))

    def test_verilmeyen_alan_varsayilani_bozmaz(self, istemci):
        """Gönderilmediğinde kurucunun kendi varsayılanı yürür."""
        _, a, ham_a = self._ozet(istemci)
        _, b, ham_b = self._ozet(istemci, {'fin_effect': True,
                                           'wall_roughness': 5.0e-6})
        assert ham_a == ham_b


# ===========================================================================
# P7B2-20 — _ThreadLocalLineDedup akış sözleşmesi
# ===========================================================================
class _SahteAkis(io.TextIOBase):
    encoding = 'utf-8'
    errors = 'strict'
    line_buffering = True
    name = '<sahte>'

    def __init__(self):
        self._yazilan = []
        self.buffer = object()

    def write(self, s):
        self._yazilan.append(s)
        return len(s)

    def fileno(self):
        return 7

    def isatty(self):
        return False

    def reconfigure(self, **kw):
        return 'reconfigured'


class TestP7B220StdoutSarmalayici:
    """ÖLÇÜLDÜ (``a3/once.json`` K5): süzgeç ``sys.stdout`` üstüne SÜREÇ
    GENELİNDE takılıyor ve altındaki akışın sözleşmesini taşımıyordu —
    ``encoding`` utf-8 -> **None**, ``errors`` strict -> **None**,
    ``buffer`` -> **AttributeError**, ``line_buffering`` ->
    **AttributeError**, ``reconfigure`` -> **AttributeError**,
    ``fileno()`` 7 -> **io.UnsupportedOperation**. Depoda bu dördünü okuyan
    kod var.
    """

    @pytest.fixture()
    def sarmalayici(self):
        from hrma.app import _ThreadLocalLineDedup
        return _ThreadLocalLineDedup(_SahteAkis())

    def test_encoding_devredilir(self, sarmalayici):
        assert sarmalayici.encoding == 'utf-8'

    def test_errors_devredilir(self, sarmalayici):
        assert sarmalayici.errors == 'strict'

    def test_buffer_devredilir(self, sarmalayici):
        assert sarmalayici.buffer is sarmalayici.target.buffer

    def test_line_buffering_devredilir(self, sarmalayici):
        assert sarmalayici.line_buffering is True

    def test_fileno_devredilir(self, sarmalayici):
        assert sarmalayici.fileno() == 7

    def test_reconfigure_devredilir(self, sarmalayici):
        assert sarmalayici.reconfigure(encoding='utf-8') == 'reconfigured'

    def test_suzgec_davranisi_bozulmadi(self, sarmalayici):
        """Devretme, tekrar bastırmayı DEĞİŞTİRMEZ."""
        sarmalayici.begin_scope()
        sarmalayici.write('ayni satir\n')
        sarmalayici.write('ayni satir\n')
        sarmalayici.write('baska satir\n')
        durum = sarmalayici.end_scope()
        assert durum['total'] == 3
        assert sarmalayici.target._yazilan == ['ayni satir\n',
                                               'baska satir\n']

    def test_hedefte_alan_yoksa_patlamaz(self):
        """Kodlaması olmayan bir akış altta olursa devretme çökmez."""
        from hrma.app import _ThreadLocalLineDedup
        s = _ThreadLocalLineDedup(io.StringIO())
        assert s.encoding is None
        assert s.line_buffering is False


# ===========================================================================
# P7B2-21 / P7B2-22 — /parametric-analysis (İKİSİ DE ÇÜRÜTÜLDÜ)
# ===========================================================================
PARAM = {'param_type': 'chamber_pressure', 'param_start': 20.0,
         'param_end': 40.0, 'param_steps': 3, 'thrust': 1000.0,
         'burn_time': 5.0, 'of_ratio': 6.0, 'chamber_pressure': 30.0,
         'nozzle_type': 'conical', 'motor_type': 'hybrid'}
PARAM_YORUNGE = dict(PARAM, include_trajectory=True,
                     vehicle_mass_dry=12.0, vehicle_diameter=0.12,
                     launch_angle=85.0, launch_altitude=100.0)


class TestP7B221TekilAnalizor:
    """ÇÜRÜTÜLDÜ (``a3/once_k6.json``). Kalem "istek sonrası nesnede
    vehicle_mass_dry=500 duruyor" diyor. ÖLÇÜM (yörünge kolu FİİLEN koştu:
    3 nokta, ``max_altitude`` yanıtta): modül düzeyindeki
    ``trajectory_analyzer``ın altı alanının HİÇBİRİ değişmiyor
    (``tekil_sizinti = {}``). ÖH D23 / P4B3-28 taramaya kendi analizörünü
    (``_tarama_analizoru``) kurdurmuş. İlk ölçüm ``analysis_type`` anahtarı
    kullandığı için yörünge kolu hiç koşmamıştı; kolu çalıştıran anahtar
    ``include_trajectory``dir — bu bekçi onu kullanır.

    İkinci ayak ("yanıt hangi aracın kullanıldığını yankılamıyor") da
    ölçümle karşılanmıştır: araç alanları GÖNDERİLMEDİĞİNDE
    ``defaults_applied`` onları adıyla beyan ediyor; gönderildiğinde
    kullanıcının kendi sayısı aynen kullanılıyor (ikame yok).
    """

    def test_tekil_nesne_istekten_etkilenmez(self, istemci):
        """ÖH D33 · OH-UC-07 (fix-36b, 16 Eyl 2026): paylaşılan modül düzeyi
        ``trajectory_analyzer`` KALDIRILDI (ölü nesne; ürün global okuma 0).
        Eski ayak paylaşılan nesnenin istekten etkilenmediğini ölçüyordu; yeni
        ayak paylaşılan nesnenin VAR OLMADIĞINI kilitler (yapısal, AST) ve
        yörünge kolunun aynı gövdeyle koşmaya devam ettiğini doğrular."""
        import ast
        import hrma.app as A
        assert not hasattr(A, 'trajectory_analyzer'), (
            'modul duzeyi paylasilan TrajectoryAnalyzer geri geldi (OH-UC-07)')
        agac = ast.parse((KOK / 'hrma' / 'app.py').read_text(encoding='utf-8'))
        modul_duzeyi = [
            n.lineno for n in agac.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'trajectory_analyzer'
                    for t in n.targets)]
        assert modul_duzeyi == [], modul_duzeyi
        kod, j, ham = gonder(istemci, '/parametric-analysis', PARAM_YORUNGE)
        assert kod == 200, kod
        assert 'max_altitude' in ham.decode('utf-8'), 'yörünge kolu koşmadı'

    def test_verilmeyen_arac_alani_beyan_edilir(self, istemci):
        gv = {k: v for k, v in PARAM_YORUNGE.items()
              if k not in ('vehicle_mass_dry', 'vehicle_diameter')}
        kod, j, _ = gonder(istemci, '/parametric-analysis', gv)
        assert kod == 200, kod
        beyan = {b['field'] for b in (j.get('defaults_applied') or [])}
        assert {'vehicle_mass_dry', 'vehicle_diameter'} <= beyan


class TestP7B222SupurmeAraligi:
    """ÇÜRÜTÜLDÜ (``a3/once.json`` K7). Kalem "param_start/param_end için
    hiç kapı yok" diyor; ölçüm TABAN AĞACINDA üç kapıyı da buluyor:
    ``'abc'`` -> 422 ``invalid_sweep_interval`` (ham NumPy metniyle 400
    DEĞİL), ``start == end`` -> 422 ``degenerate_sweep_interval``
    (``status='success'`` DEĞİL), alan hiç yok -> 422
    ``sweep_interval_not_supplied``. Bekçi kapıların KAYBOLMAMASINI kilitler.
    """

    def test_metin_422(self, istemci):
        kod, j, _ = gonder(istemci, '/parametric-analysis',
                           dict(PARAM, param_start='abc'))
        assert kod == 422, kod
        assert j['error'] == 'invalid_sweep_interval'

    def test_yozlasmis_aralik_422(self, istemci):
        kod, j, _ = gonder(istemci, '/parametric-analysis',
                           dict(PARAM, param_start=20.0, param_end=20.0))
        assert kod == 422, kod
        assert j['error'] == 'degenerate_sweep_interval'

    def test_verilmeyen_alan_422(self, istemci):
        gv = {k: v for k, v in PARAM.items() if k != 'param_start'}
        kod, j, _ = gonder(istemci, '/parametric-analysis', gv)
        assert kod == 422, kod
        assert j['error'] == 'sweep_interval_not_supplied'


# ===========================================================================
# P7B2-23 — /api/slosh-analysis iki hata dili
# ===========================================================================
SLOSH = {'radius': 0.3, 'fill_height': 0.6, 'g_eff': 9.81,
         'fluid_density': 810.0, 'baffle_width_ratio': 0.15,
         'baffle_depth_ratio': 0.10}


class TestP7B223IkiHataDili:
    """ÖLÇÜLDÜ (``a3/once.json`` K8): aynı alan, aynı sınıf hata, iki dil —
    ``control_frequencies: ['abc']`` -> ham ``could not convert string to
    float: 'abc'`` (alan adı YOK); ``control_frequencies: 'abc'`` ->
    ``'control_frequencies' must be a list of frequencies [Hz]``.
    ``structural_frequencies`` de aynı ikiliği taşıyordu.
    """

    @staticmethod
    def _hata(istemci, ek):
        kod, j, _ = gonder(istemci, '/api/slosh-analysis', dict(SLOSH, **ek))
        return kod, str(j.get('error'))

    def test_liste_kolu_alan_adini_soyluyor(self, istemci):
        kod, hata = self._hata(istemci, {'control_frequencies': ['abc']})
        assert kod == 400
        assert 'control_frequencies' in hata
        assert 'could not convert string to float' not in hata

    def test_iki_kol_ayni_dili_konusuyor(self, istemci):
        _, liste = self._hata(istemci, {'control_frequencies': ['abc']})
        _, dize = self._hata(istemci, {'control_frequencies': 'abc'})
        assert liste == dize

    def test_kardes_alan_da_ayni(self, istemci):
        kod, hata = self._hata(istemci, {'structural_frequencies': ['xyz']})
        assert kod == 400
        assert 'structural_frequencies' in hata
        assert "'xyz'" in hata

    def test_saglikli_iki_kol_ayni_sonucu_verir(self, istemci):
        kod_a, ja, _ = gonder(istemci, '/api/slosh-analysis',
                              dict(SLOSH, control_frequencies=[1.0, 2.0]))
        kod_b, jb, _ = gonder(istemci, '/api/slosh-analysis',
                              dict(SLOSH, control_frequencies='1.0,2.0'))
        assert (kod_a, kod_b) == (200, 200)
        assert ja == jb


# ===========================================================================
# P7B3-11 — molecular_weight aynı anahtar iki tip
# ===========================================================================
class TestP7B311MolekulAgirligiTipi:
    """ÖLÇÜLDÜ (``a3/once.json`` K9, dokuz itici): ``paraffin`` -> ``352``
    (**int**), diğer sekizi float. Aynı anahtar iki JSON tipi taşıyordu.
    """

    ITICILER = ('htpb', 'rp1', 'paraffin', 'oxygen', 'lox', 'n2o',
                'hydrogen', 'mmh', 'abs')

    def test_tek_tip(self, istemci):
        tipler = {}
        for ad in self.ITICILER:
            kod, j, _ = gonder(istemci, '/api/get-propellant-properties',
                               {'propellant_name': ad,
                                'propellant_type': 'hybrid_fuel'})
            assert kod == 200, (ad, kod)
            mw = (j.get('properties') or {}).get('molecular_weight')
            assert mw is not None, ad
            tipler[ad] = type(mw).__name__
        assert set(tipler.values()) == {'float'}, tipler

    def test_sayi_degismedi(self, istemci):
        """Tip birleşir, DEĞER birleşmez: 352 -> 352.0 (aynı sayı)."""
        _, j, _ = gonder(istemci, '/api/get-propellant-properties',
                         {'propellant_name': 'paraffin',
                          'propellant_type': 'hybrid_fuel'})
        assert j['properties']['molecular_weight'] == 352.0
        assert j['properties']['molecular_weight_unit'] == 'g/mol'

    def test_cozulemeyen_deger_uydurulmaz(self):
        """Dize kolu (PubChem) çözülemezse alan YAYIMLANMAZ, 0'a düşmez."""
        kaynak = APP_PY.read_text(encoding='utf-8')
        assert "merged_props.pop('molecular_weight', None)" in kaynak
        assert "'molecular_weight_unresolved'" in kaynak

    def test_dize_deger_cozulur(self, istemci):
        """PubChem kolunun ürettiği dize biçimi float'a çevrilir."""
        import hrma.app as A
        with contextlib.redirect_stdout(io.StringIO()):
            ham = A.propellant_db.get_propellant_properties('htpb')
        assert ham is not None
        assert isinstance(float(str(ham.get('molecular_weight', 1))), float)


# ===========================================================================
# P7B3-33 — /api/fea/planar-grain üst basınç kapısı
# ===========================================================================
GRAIN = {'grain_type': 'bates', 'propellant_type': 'apcp',
         'outer_diameter_mm': 100.0, 'core_diameter_mm': 30.0,
         'chamber_pressure_bar': 40.0, 'max_rounds': 0}


class TestP7B333UstBasincKapisi:
    """ÖLÇÜLDÜ (``a3/once.json`` K10): ``chamber_pressure_bar = 1e9`` HTTP
    **200** + ``bore.max_strain = 249878,96`` (yani %25 milyon uzama)
    "doğrusal elastik sonuç" olarak yayımlanıyordu; ``strain_margin``
    sessizce ``None``, uyarı bloğu boştu. 201 bar da 200 dönüyordu.
    Alt uç kapalıydı (0 / -40 -> 400), kapalı olmayan ÜST uçtu.
    """

    def test_asiri_basinc_reddedilir(self, istemci):
        kod, j, _ = gonder(istemci, '/api/fea/planar-grain',
                           dict(GRAIN, chamber_pressure_bar=1.0e9))
        assert kod == 422, kod
        assert j['error'] == 'chamber_pressure_out_of_range'
        assert j['invalid_fields'][0]['field'] == 'chamber_pressure_bar'

    def test_bant_tek_kaynaktan(self, istemci):
        """Sayı bu dosyada da uçta da YAZILI DEĞİL: kanondan gelir."""
        from hrma.validation.motor_validation import FORM_LIMITS
        alt, ust, birim = FORM_LIMITS['solid']['chamber_pressure']
        kod, j, _ = gonder(istemci, '/api/fea/planar-grain',
                           dict(GRAIN, chamber_pressure_bar=ust + 1.0))
        assert kod == 422, kod
        kunye = j['invalid_fields'][0]
        assert kunye['accepted_range'] == [alt, ust]
        assert kunye['unit'] == birim
        assert kunye['motor_form'] == 'solid'

    def test_bant_ust_ucu_kabul_edilir(self, istemci):
        from hrma.validation.motor_validation import FORM_LIMITS
        ust = FORM_LIMITS['solid']['chamber_pressure'][1]
        kod, j, _ = gonder(istemci, '/api/fea/planar-grain',
                           dict(GRAIN, chamber_pressure_bar=float(ust)))
        assert kod == 200, kod
        assert j['fea']['status'] == 'ok'

    def test_saglikli_kosum_bit_ayni(self, istemci):
        """ÖK-22: bant içi koşum DEĞİŞMEZ."""
        kod, j, _ = gonder(istemci, '/api/fea/planar-grain', dict(GRAIN))
        assert kod == 200, kod
        assert j['fea']['bore']['max_strain'] == pytest.approx(
            0.009995158207145551, rel=1e-9)

    def test_kardes_uc_ile_ayni_bant(self, istemci):
        """``/calculate_solid`` aynı sayıyı aynı yerden uyguluyor."""
        kaynak = APP_PY.read_text(encoding='utf-8')
        assert kaynak.count(
            "_form_band_kapisi(params['chamber_pressure_bar'], 'solid'") == 1


# ===========================================================================
# P7B4-07 — /api/flow-analysis kesirli n_stations
# ===========================================================================
FLOW = {'chamber_pressure': 70.0, 'chamber_temperature': 3500.0,
        'gamma': 1.2, 'molecular_weight': 24.0, 'throat_diameter': 0.10,
        'expansion_ratio': 25.0, 'ambient_pressure': 0.0}


class TestP7B407KesirliIstasyonSayisi:
    """ÖLÇÜLDÜ (``a3/once.json`` K11): bant kapısı ``int(...)``ten SONRA
    koşuyordu, yani kesirli değer önce tabana yuvarlanıyordu.
    ``n_stations = 30,7`` -> HTTP **200**, yayımlanan ızgara **30**
    (uyarı yok, beyan yok); ``n_stations = 2,7`` -> 400 ama gerekçe
    "got **2**" diyordu, kullanıcının gönderdiği sayı reddin metninde
    yanlış yazılıydı. Kardeş kapı (``/api/cfd/nozzle`` ``max_iterations``)
    aynı sınıfı "must be a WHOLE number" ile reddediyor.
    """

    def test_bant_ici_kesirli_deger_reddedilir(self, istemci):
        kod, j, _ = gonder(istemci, '/api/flow-analysis',
                           dict(FLOW, n_stations=30.7))
        assert kod == 400, kod
        assert 'WHOLE number' in str(j.get('error'))
        assert j['invalid_fields'][0]['reason'] == 'not_a_whole_number'

    def test_ret_gonderilen_sayiyi_dogru_yaziyor(self, istemci):
        kod, j, _ = gonder(istemci, '/api/flow-analysis',
                           dict(FLOW, n_stations=2.7))
        assert kod == 400, kod
        assert j['invalid_fields'][0]['value'] == pytest.approx(2.7)
        assert '2.7' in str(j.get('error'))

    def test_tam_sayi_bandi_korunur(self, istemci):
        from hrma.app import FLOW_N_STATIONS_MIN, FLOW_N_STATIONS_MAX
        for deger in (0, -5, 10 ** 7):
            kod, j, _ = gonder(istemci, '/api/flow-analysis',
                               dict(FLOW, n_stations=deger))
            assert kod == 400, (deger, kod)
            assert j['invalid_fields'][0]['reason'] == 'out_of_range'
        kod, j, _ = gonder(istemci, '/api/flow-analysis',
                           dict(FLOW, n_stations=FLOW_N_STATIONS_MIN))
        assert kod == 200, kod
        assert FLOW_N_STATIONS_MIN < FLOW_N_STATIONS_MAX

    def test_kesirli_ama_tam_degerli_float_kabul(self, istemci):
        """``45.0`` bir tam sayıdır; JSON tipi yüzünden reddedilmez."""
        kod, _, ham_a = gonder(istemci, '/api/flow-analysis',
                               dict(FLOW, n_stations=45.0))
        kod_b, _, ham_b = gonder(istemci, '/api/flow-analysis',
                                 dict(FLOW, n_stations=45))
        assert (kod, kod_b) == (200, 200)
        assert ham_a == ham_b

    def test_verilmeyen_alan_bit_ayni(self, istemci):
        """ÖK-22: alan gönderilmediğinde varsayılan yolu değişmez."""
        kod, j, _ = gonder(istemci, '/api/flow-analysis', dict(FLOW))
        assert kod == 200, kod
        assert '"n_stations": 45' in json.dumps(j)
