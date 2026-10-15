"""ÖH Dalga-27 · ihracat kulvarı · aşama a1 — bekçiler.

Kapsam
======
* **P13B2-09** (defter, D26 devri) — ``cad_visualization._add_fallback_3d_motor``
  yedek 3B yolu base64 ``bdata`` üretiyordu; vendor plotly.js 1.58.5 bu biçimi
  çözemediği için mesh düştüğünde 3B görünüm SESSİZCE boş kalıyordu.
  Ölçüm: ``docs/scofield/raw/OH/D27/ihracat/a1/once_p13b209.json`` (6 blok)
  -> ``sonra_p13b209.json`` (0 blok).
* **P13B4-10 bekçi borcu** (ihracat payı) — kapalı kalemlerin sembolünü
  DOĞRUDAN sınayan bekçiler. Bu bölüm kapalı kalemi yeniden AÇMAZ; yalnız
  onarımın kodda durduğunu sembol düzeyinde çapalar.

Bekçi felsefesi: sayı değil İLİŞKİ sınanır (fail-closed). "bdata 0" hükmü,
çizimin GERÇEKTEN üretildiği doğrulanmadan verilmez — yoksa boş figür de
sıfır bdata verir ve bekçi boşa koşar.
"""

import json
import pathlib
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
KANIT = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D27' / 'ihracat' / 'a1'

#: Sondaların kullandığı asgari motor ölçüleri (metre). Uydurma SONUÇ değil,
#: yalnız çizicinin çalışabilmesi için gereken geometri GİRDİSİ.
SONDA_MOTORU = {
    'chamber_diameter': 0.1,
    'chamber_length': 0.5,
    'throat_diameter': 0.04,
    'exit_diameter': 0.12,
    'nozzle_length': 0.2,
    'motor_name': 'd27_ihracat_sonda',
}


def _bdata_sayisi(cikti):
    metin = cikti if isinstance(cikti, str) else json.dumps(cikti, default=str)
    return metin.count('"bdata"'), len(metin)


def _bos_altfigur():
    """``_create_plotly_visualization``in kullandığı 2x2 alt figür düzeni."""
    from plotly.subplots import make_subplots
    return make_subplots(
        rows=2, cols=2,
        specs=[[{'type': 'scene', 'colspan': 2}, None],
               [{'type': 'xy'}, {'type': 'xy'}]])


def _tasarimci():
    from hrma.export.cad_visualization import MotorCADDesigner
    return MotorCADDesigner()


# ===========================================================================
# P13B2-09 — yedek 3B yol base64 bdata yazmamalı
# ===========================================================================
class TestP13B209YedekYolBdataYazmiyor:
    """Mesh düştüğünde devreye giren yedek yolun ÇIKTISI denetlenir.

    Üç ayrı soru sorulur, üçü de gerekli:

    1. ``_add_fallback_3d_motor`` çıktısında bdata var mı?  (kusurun kendisi)
    2. Yedek yol gerçekten ÇİZDİ mi?  (bekçi boşa koşmasın)
    3. Diziler plotly'ye hangi TİPLE gidiyor?  (mekanizma — plotly'nin
       serileştirme davranışı değişse bile kusur yakalanır)
    """

    def test_yardimci_ciktisinda_bdata_yok(self):
        fig = _bos_altfigur()
        _tasarimci()._add_fallback_3d_motor(fig, SONDA_MOTORU, row=1, col=1)
        sayi, uzunluk = _bdata_sayisi(fig.to_json())
        assert sayi == 0, (
            '_add_fallback_3d_motor çıktısında %d base64 "bdata" bloğu var '
            '(JSON %d bayt). Vendor plotly.js 1.58.5 bu biçimi çözemez: '
            'mesh düştüğünde 3B görünüm SESSİZCE boş kalır ve kullanıcı '
            'uyarı almaz (defter P13B2-09).' % (sayi, uzunluk))

    def test_yedek_yol_gercekten_cizdi(self):
        """Sıfır bdata hükmü boş figürden gelmesin (fail-closed)."""
        fig = _bos_altfigur()
        _tasarimci()._add_fallback_3d_motor(fig, SONDA_MOTORU, row=1, col=1)
        adlar = sorted(iz.name for iz in fig.data)
        assert adlar == ['Chamber', 'Nozzle'], (
            'yedek 3B yol beklenen iki yüzeyi çizmedi (bulunan: %r) — '
            'bdata sayacı boş figür üzerinde koşuyorsa bekçi kördür.'
            % (adlar,))

    def test_izler_numpy_dizisi_tasimiyor(self):
        """MEKANİZMA bekçisi: dizi plotly'ye numpy olarak gitmemeli.

        plotly 6.x yalnız ``ndarray`` gördüğünde base64 ``bdata`` yazar;
        düz liste düz JSON'a iner. Çıktı bekçisi bugünkü plotly davranışına
        bağlı, bu bekçi ise KÖKE bağlı: sürüm değişse de kusur yakalanır.
        """
        import numpy as np
        fig = _bos_altfigur()
        _tasarimci()._add_fallback_3d_motor(fig, SONDA_MOTORU, row=1, col=1)
        suclu = []
        for iz in fig.data:
            for eksen in ('x', 'y', 'z'):
                deger = getattr(iz, eksen, None)
                if isinstance(deger, np.ndarray):
                    suclu.append('%s.%s' % (iz.name, eksen))
        assert not suclu, (
            'yedek 3B yol plotly\'ye numpy dizisi veriyor: %r — '
            'fig.to_json() bunları base64 bdata yazar (P13B2-09). '
            'Çözüm: .tolist() ya da _fig_json kapısı.' % (suclu,))

    def test_ucdan_uca_mesh_dusunce_bdata_yok(self):
        """Gerçek ürün yolu: mesh listesi boş -> yedek -> yayımlanan JSON."""
        cikti = _tasarimci()._create_plotly_visualization([], SONDA_MOTORU)
        sayi, uzunluk = _bdata_sayisi(cikti)
        assert sayi == 0, (
            '_create_plotly_visualization çıktısında %d bdata bloğu var '
            '(JSON %d bayt) — P13B2-09 geri geldi.' % (sayi, uzunluk))
        assert 'Chamber' in cikti and 'Nozzle' in cikti, (
            'uçtan uca yol yedek çizimi yayımlamadı; sıfır bdata hükmü '
            'boşluktan geliyor olabilir.')

    def test_borc_imi_kaldirildi(self):
        """P13B2-09 xfail(strict) borç imi geri konmamalı."""
        from tests.test_fig_json_gate import BUGUN_BDATA_URETEN
        assert '_create_plotly_visualization' not in BUGUN_BDATA_URETEN, (
            'P13B2-09 borç imi geri konmuş — ürün D27 ihracat a1 ile '
            'onarıldı (bdata 6 -> 0).')

    def test_olcum_dosyalari_kanit_diziniyle_tutarli(self):
        """Rapordaki 6 -> 0 iddiası kanıt dosyalarında duruyor mu?"""
        once = json.loads((kanit_gerekli(KANIT / 'once_p13b209.json')).read_text('utf-8'))
        sonra = json.loads((kanit_gerekli(KANIT / 'sonra_p13b209.json')).read_text('utf-8'))
        assert once['sonda_bdata']['_create_plotly_visualization']['bdata'] == 6
        assert once['yardimci_bdata']['_add_fallback_3d_motor']['bdata'] == 6
        assert sonra['sonda_bdata']['_create_plotly_visualization']['bdata'] == 0
        assert sonra['yardimci_bdata']['_add_fallback_3d_motor']['bdata'] == 0
        # Sayaç kör olsaydı 'once' de 0 görünürdü.
        assert once['sayac_kor_degil'] and sonra['sayac_kor_degil']
        # İz sayısı DEĞİŞMEDİ: onarım çizimi kaldırmadı, biçimini indirdi.
        assert (once['yardimci_bdata']['_add_fallback_3d_motor']['iz']
                == sonra['yardimci_bdata']['_add_fallback_3d_motor']['iz'] == 2)

    def test_mesh_yolu_ile_yedek_yol_ayni_korumaya_sahip(self):
        """İLİŞKİ bekçisi: iki yol da aynı bdata korumasını taşımalı.

        Kusurun kökü asimetriydi — mesh yolunda (v2.5.2) ``.tolist()`` vardı,
        yedek yolda yoktu. Bu bekçi asimetrinin geri gelmesini yasaklar:
        ``_create_plotly_visualization`` içindeki HER ``go.Surface`` /
        ``go.Mesh3d`` çağrısının dizi argümanları ``.tolist()`` sonucu olmalı.
        """
        import ast
        kaynak = (REPO_ROOT / 'hrma' / 'export' / 'cad_visualization.py')
        agac = ast.parse(kaynak.read_text(encoding='utf-8'))
        hedefler = {'_create_plotly_visualization', '_add_fallback_3d_motor'}
        ciplak = []
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.FunctionDef)
                    and dugum.name in hedefler):
                continue
            for cagri in ast.walk(dugum):
                if not (isinstance(cagri, ast.Call)
                        and isinstance(cagri.func, ast.Attribute)
                        and cagri.func.attr in ('Surface', 'Mesh3d')):
                    continue
                for kw in cagri.keywords:
                    if kw.arg not in ('x', 'y', 'z', 'i', 'j', 'k'):
                        continue
                    duz = (isinstance(kw.value, ast.Call)
                           and isinstance(kw.value.func, ast.Attribute)
                           and kw.value.func.attr == 'tolist')
                    if not duz:
                        ciplak.append('%s:%d %s.%s'
                                      % (dugum.name, cagri.lineno,
                                         cagri.func.attr, kw.arg))
        assert not ciplak, (
            '3B iz dizisi düz listeye çevrilmeden plotly\'ye veriliyor: %r — '
            'P13B2-09 tam olarak bu asimetriden doğmuştu (mesh yolu korumalı, '
            'yedek yol korumasız).' % (ciplak,))


# ===========================================================================
# P13B4-10 bekçi borcu (ihracat payı) — P9B5-01
# ===========================================================================
# ÖLÇÜM (once_bekci_borcu.json, A bölümü): ihracat payındaki 9 kalemin
# 8'inde kalem kimliğini ANAN ve sembolünü ÇAĞIRAN bir test zaten vardı
# (P9B1-02 test_z5s_cadgeo + test_d26_ihracat_a1, P9B2-07/-25
# test_z5guard_ihrac_veri, P9B3-01 test_export_real_data, P9B3-09
# test_z5s_ihracat_kapisi, P9B4-01 test_d15_ihracat_a3, P9B4-04
# test_z5guard_ihrac_veri, P9B4-08 test_d16_yapisal_sistem_a1) — yani
# dağıtım dosyasındaki boş ``odendi`` alanı BAYAT. Borcu gerçekten AÇIK olan
# tek kalem P9B5-01'dir: ``validate_oxidizer_state`` sembolü tests/ altında
# HİÇ çağrılmıyordu ve kalem kimliği yalnız borç LİSTESİNDE geçiyordu.
#
# Mevcut tek dolaylı bekçi (test_fazb_yogunluk_matrisi
# ::test_dogrulama_bandi_deponun_KENDI_kanonunu_reddetmiyor) kalemin yalnız
# BİR bacağını tutuyor: "doğruyu reddetme". Kalemin ikinci ve daha tehlikeli
# bacağı — "kendi YANLIŞ 1220'sini GEÇİRİYOR" — bekçisizdi.
class TestBekciBorcuP9B501OksitleyiciDurumKapisi:
    """P9B5-01 (kapalı, doğrudan bekçisi YOKTU): iki kademeli zarf.

    Kusur (Z1 öncesi): ``validate_data`` oksitleyici yolunda tek skaler bant
    ``800 < rho < 1500`` uyguluyordu. Bu bant

      * N₂O'nun 293,15 K'deki GERÇEK yoğunluğunu (785,10) reddediyor,
      * reddedilen değerin yerine çağıranın koyduğu YANLIŞ 1220'yi
        (kaynama noktası yoğunluğu, 293,15 K'de +%55,4) geçiriyordu.

    Yani kapı, kapıdan daha kötü bir şeye açılıyordu. Ölçüm:
    ``once_bekci_borcu.json`` B bölümü.
    """

    @staticmethod
    def _dogrula(**veri):
        from hrma.data.external_data_fetcher import ExternalDataFetcher
        return ExternalDataFetcher().validate_data(dict(veri), 'oxidizer')

    def test_gercek_n2o_yogunlugu_gecer(self):
        """Kalemin birinci bacağı: doğru sayı reddedilmemeli."""
        gecerli, mesaj = self._dogrula(
            fluid='n2o', temperature=293.15, density=785.10, viscosity=6.5e-5)
        assert gecerli, (
            'N₂O 293,15 K gerçek yoğunluğu (785,10 kg/m³) doğrulamadan '
            'geçemiyor: %s — eski skaler bant (800 < rho < 1500) geri '
            'gelmiş olabilir.' % mesaj)

    def test_yanlis_1220_REDDEDILIR(self):
        """Kalemin ikinci bacağı — BEKÇİSİ OLMAYAN bacak.

        1220 kg/m³ N₂O'nun kaynama noktası (184,67 K) yoğunluğudur; oda
        koşulunda kullanılması +%55,4 yoğunluk, enjektör alanında −%19,8
        hata demektir. Eski bant bu sayıyı GEÇİRİYORDU.
        """
        gecerli, mesaj = self._dogrula(
            fluid='n2o', temperature=293.15, density=1220.0, viscosity=6.5e-5)
        assert not gecerli, (
            'N₂O için 293,15 K\'de 1220 kg/m³ doğrulamadan GEÇTİ — bu değer '
            'kaynama noktası yoğunluğudur, oda koşulunda %+55,4 hatadır '
            '(defter P9B5-01).')
        assert '785' in mesaj and '1220' in mesaj, (
            'ret mesajı ölçülen ile referansı ADIYLA söylemiyor (fail-closed '
            'gerekçe): %r' % mesaj)

    def test_eski_bandin_ORTASI_da_reddedilir(self):
        """948,80 eski bandın tam ortasıydı; durum denetimi onu da eler."""
        gecerli, mesaj = self._dogrula(
            fluid='n2o', temperature=293.15, density=948.80, viscosity=6.5e-5)
        assert not gecerli, (
            '948,80 kg/m³ geçti — eski skaler bandın ortasındaki değerler '
            'durum tutarlılığı denetimine takılmalıydı: %s' % mesaj)

    def test_eksik_yogunluk_EKSIK_diye_reddedilir(self):
        """Eksik alan 0'a çevrilip 'anormal' DENMEZ; EKSİK diye reddedilir.

        Eski kod ``data.get('density', 0)`` ile eksikliği 0'a çeviriyor ve
        "Abnormal density" diyordu: yani "alan yok" ile "alan yanlış"
        ayırt EDİLEMİYORDU. İki hâlin gerekçesi farklıdır, çünkü çözümleri
        farklıdır (biri veri sağlayıcı sorunu, diğeri hâl hatası). Bekçi ret
        olgusuna değil ret GEREKÇESİNE bakar; yoksa kusurlu sürüm de yeşil
        verirdi (ölçüldü: mutasyon_p9b501.json).
        """
        gecerli, mesaj = self._dogrula(
            fluid='n2o', temperature=293.15, viscosity=6.5e-5)
        assert not gecerli, 'yoğunluk yokken doğrulama GEÇTİ (fail-open)'
        assert 'missing' in mesaj.lower(), (
            'eksik yoğunluk EKSİK diye değil başka bir gerekçeyle '
            'reddediliyor (%r) — eski .get(key, 0) davranışı geri gelmiş '
            'olabilir: o sürüm eksikliği 0 sayıp "Abnormal density" '
            'diyordu.' % mesaj)
        assert 'abnormal' not in mesaj.lower(), (
            'eksik alan "anormal" diye anılıyor: %r' % mesaj)

    def test_kimlik_yoksa_SINIR_BEYAN_EDILIR(self):
        """Akışkan/sıcaklık yoksa durum denetimi koşamaz — bunu SÖYLEMELİ.

        Bu bir muafiyet değil künyedir: geçen sayı yalnız mutlak zarftan
        geçmiştir ve mesaj bunu açıkça yazar (beyan, çözümün yerine geçmez;
        burada zaten çözülecek bir şey yoktur — girdi eksiktir).
        """
        gecerli, mesaj = self._dogrula(density=1220.0, viscosity=6.5e-5)
        assert gecerli, mesaj
        assert 'absolute envelope only' in mesaj, (
            'durum denetiminin KOŞMADIĞI mesajda beyan edilmiyor: %r' % mesaj)

    def test_tek_bant_geri_gelmedi(self):
        """İLİŞKİ bekçisi: dört oksitleyicinin zarfı AYRIŞIK olmalı.

        Kusurun kökü "tek bant, dört akışkan" idi. Zarflar aynılaşırsa
        (ya da tek bir tabloya inerse) kusur mekanizma düzeyinde geri
        gelmiş demektir — sayıya değil AYRIŞIKLIĞA bakılır.
        """
        from hrma.data.external_data_fetcher import (
            OXIDIZER_DENSITY_ENVELOPE)
        assert len(OXIDIZER_DENSITY_ENVELOPE) >= 4, (
            'oksitleyici yoğunluk zarfı %d akışkan tanıyor; tek bant '
            'yaklaşımı geri gelmiş olabilir.' % len(OXIDIZER_DENSITY_ENVELOPE))
        bantlar = {ad: tuple(b) for ad, b in OXIDIZER_DENSITY_ENVELOPE.items()}
        assert len(set(bantlar.values())) > 1, (
            'tüm akışkanlar AYNI bandı paylaşıyor: %r — P9B5-01 tam olarak '
            'bu tekleşmeden doğmuştu.' % (bantlar,))

    def test_olcum_dosyasi_borc_envanteriyle_tutarli(self):
        """Rapordaki "9 kalemden 8'i zaten bekçili" iddiasının çapası."""
        o = json.loads((kanit_gerekli(KANIT / 'once_bekci_borcu.json')).read_text('utf-8'))
        env = o['A_bekci_envanteri']
        bekcisiz = sorted(k for k, v in env.items()
                          if not v['dogrudan_bekci_var'])
        assert bekcisiz == ['P9B5-01'], (
            'borç envanteri değişmiş: bekçisiz kalemler %r (ölçüm: yalnız '
            'P9B5-01).' % (bekcisiz,))
        b = o['B_p9b501_davranis']
        assert b['n2o_gercek_785']['gecerli'] is True
        assert b['n2o_yanlis_1220']['gecerli'] is False
        assert b['n2o_bant_ortasi_948_8']['gecerli'] is False
        assert b['yogunluk_yok']['gecerli'] is False
