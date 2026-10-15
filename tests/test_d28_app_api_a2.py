"""OH Dalga-28 / app-api asama-2 bekcileri (P07 + P16 havuzu, 11 kalem).

Kanit: ``docs/scofield/raw/OH/D28/app-api/a2/`` (``olcum.py`` + ``once.json``,
``olcum2.py`` + ``once2.json``, ``mutasyon.py`` + ``mutasyon.json``,
``rapor.md``). Taban ``7cd08bcc``.

Kalemler ve hukumleri:

  P16B1-35  curutuldu  taninmayan analiz turu ZATEN 422 (D24 / P7B2-10)
  P16B1-37  curutuldu  bant urun alan adiyla ULASILABILIR (Z5S / S3)
  P16B1-46  onarildi   n_holes isareti + kirpma gerekcesinin kanali
  P16B1-47  curutuldu  oxidizer_temp mutlak sifir alti ZATEN 400
  P16B1-48  curutuldu  gas_constant olu ama BEYANLI, negatifi reddediliyor
  P16B1-51  onarildi   safety_factor bandi uc kapisinda, tek kaynak
  P16B2-09  curutuldu  chamber_temperature kati/sivida BEYANLI olu
  P16B3-20  onarildi   n_stations sessiz kirpma bitti, bant tek kaynak
  P16B3-21  onarildi   FEA mesh cozunurlugu: imkansiz reddedilir, butce beyanli
  P16B3-23  onarildi   /api/fea/thermal ortam sicakligi kapisi
  P16B3-24  kismen     TNT tablosu htpb tasimiyor (yapisal-sistem borcu)

Turkce metinler ASCII yazilmistir: ``tests/support/homoglif_tarayici.py``
bekcisi tanimlayici/dugum adlarinda ASCII disi karakter aramaktadir ve bu
dosyanin dugum adlari parametre metinlerinden turemektedir.
"""
import json
import math

import pytest

from hrma.app import app
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.engines.hybrid_rocket_engine import (
    SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX)
from hrma.utils.injector_design import (
    InjectorDesign, InjectorPlateInputError)
from tests.support.kanit import kanit_gerekli


TABAN = {'motor_name': 'X', 'thrust': 1000, 'burn_time': 10,
         'chamber_pressure': 20, 'of_ratio': 6.0,
         'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
         'nozzle_type': 'conical', 'l_star': 1.0}

KATI = {'motor_name': 'K', 'propellant_type': 'apcp', 'grain_type': 'bates',
        'chamber_pressure': 40.0, 'thrust': 5000.0, 'burn_time': 3.0,
        'chamber_diameter': 100.0, 'grain_length': 500.0,
        'core_diameter': 30.0, 'expansion_ratio': 8.0}

SIVI = {'motor_name': 'S', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0}

WALL = {'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
        'chamber_diameter': 0.1, 'chamber_length': 0.5,
        'throat_diameter': 0.02, 'burn_time': 10.0, 'mdot_total': 1.0,
        'material': 'steel', 'cooling_type': 'natural',
        'expansion_ratio': 8.0}

GUVENLIK = {'chamber_pressure': 40.0, 'propellant_mass': 5.0,
            'chamber_diameter': 0.1, 'wall_thickness': 0.005,
            'motor_type': 'hybrid'}


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    return app.test_client()


def _alanlar(govde):
    return sorted({k.get('field') for k in (govde or {}).get(
        'invalid_fields', []) if isinstance(k, dict)})


def _yaprak_ara(nesne, ad):
    bulunan = []

    def yur(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == ad:
                    bulunan.append(v)
                yur(v)
        elif isinstance(x, list):
            for v in x:
                yur(v)
    yur(nesne)
    return bulunan


# =====================================================================
# P16B1-35 (CURUTULDU) — taninmayan analiz turu
# =====================================================================
class TestP16B135TaninmayanAnalizTuru:
    """Kalem 'HTTP 200 + bos results' diyor; olcum 422 gosterdi.

    ONCE (``a2/once.json`` K1, taban ``7cd08bcc``): ``{'analysis_types':
    ['kediler']}`` -> HTTP 422 ``unsupported_analysis_type``, 458 bayt,
    ``unsupported_analysis_types: ['kediler']``. Bos liste ve tamamen bos
    govde de 422. Kalem D24 / P7B2-10 ile KAPANMISTIR; bu bekci kapanisi
    DONDURUR (geri gelirse kirmizi verir).
    """

    @pytest.mark.parametrize('tipler', [['kediler'], [],
                                        ['3d_visualization', 'kediler']])
    def test_taninmayan_tur_422(self, istemci, tipler):
        r = istemci.post('/api/advanced-analysis',
                         json={'motor_data': {}, 'analysis_types': tipler})
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert g['error'] == 'unsupported_analysis_type'
        assert g['supported_analysis_types']

    def test_tamamen_bos_govde_de_422(self, istemci):
        r = istemci.post('/api/advanced-analysis', json={})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'unsupported_analysis_type'

    def test_liste_olmayan_tur_alani_422(self, istemci):
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': 'kediler'})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'invalid_analysis_types'


# =====================================================================
# P16B1-37 (CURUTULDU) — bant urun alan adiyla ulasilabilir
# =====================================================================
class TestP16B137TakmaAdBandi:
    """Kalem 'kanonik adla 400, urun adiyla 200' diyor; olcum IKISI DE 400.

    ONCE (``a2/once.json`` K2): dort ciftin SEKIZ isteginin sekizi de HTTP
    400 aldi ve ret govdesi GONDERILEN adi anti (kanonik istekte
    ``temperature``, urun isteginde ``chamber_temperature``). Kapatan
    onarim ``motor_validation.FIELD_ALIASES`` (OH Z5S / S3).
    """

    @pytest.mark.parametrize('urun_ad,kanonik_ad,deger', [
        ('chamber_temperature', 'temperature', -500),
        ('chamber_diameter_input', 'chamber_diameter', 1e9),
        ('chamber_length_override', 'chamber_length', 1e9),
        ('initial_port_diameter', 'port_diameter', 1e9),
    ])
    def test_urun_adi_da_bandi_gorur(self, istemci, urun_ad, kanonik_ad,
                                     deger):
        govde = dict(TABAN)
        govde[urun_ad] = deger
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 400, r.get_data(as_text=True)[:300]
        assert urun_ad in _alanlar(r.get_json())

    def test_takma_ad_tablosu_kanonik_banda_baglidir(self):
        from hrma.validation import motor_validation as mv
        for urun_ad, tanim in mv.FIELD_ALIASES.items():
            assert tanim['kanonik'] in mv.CANONICAL_LIMITS, urun_ad
            assert mv.CANONICAL_TO_PRODUCT_FIELD[tanim['kanonik']][0] == (
                urun_ad)


# =====================================================================
# P16B1-46 (ONARILDI) — n_holes isareti + kirpma kanali
# =====================================================================
class TestP16B146DelikSayisi:
    """ONCE (``a2/once.json`` K3, taban ``7cd08bcc``):

        POST /calculate {'n_holes': -12}  -> HTTP 200, 2 839 657 bayt,
            enjektor 280 delikle boyutlandi; Python uyari akisinda
            "invalid value encountered in sqrt" + "Hole diameter clamped
            to manufacturing band ...; hole count adjusted to 280"
            gorunuyor ama YANITTAKI ``injector.warnings`` dizisinde
            kirpma gerekcesi YOK (dort kayittan hicbiri kirpma degil).

    Zincir: ``d_h = 2*sqrt(A/(n*pi))`` negatif n icin NaN uretiyor,
    ``max(d_min, min(NaN, d_max))`` NaN'i yutup ``d_min``e dusuyor ve
    delik sayisi imalat bandindan yeniden cozuluyor.
    """

    def _enjektor(self, n_holes):
        inj = InjectorDesign(mdot_ox=0.5, chamber_pressure=20.0,
                             tank_pressure=50.0, oxidizer_temp=293.0,
                             oxidizer_type='n2o',
                             injector_type='showerhead')
        inj.set_showerhead_params(n_holes=n_holes)
        return inj

    @pytest.mark.parametrize('n', [-12, -1, -1e9])
    def test_negatif_delik_sayisi_reddedilir(self, n):
        with pytest.raises(InjectorPlateInputError) as ex:
            self._enjektor(n)
        assert 'n_holes' in str(ex.value)
        assert 'negative' in str(ex.value)

    @pytest.mark.parametrize('n', [1.5, float('nan'), float('inf'),
                                   'kirk', True])
    def test_sayi_olmayan_delik_sayisi_reddedilir(self, n):
        with pytest.raises(InjectorPlateInputError) as ex:
            self._enjektor(n)
        assert 'n_holes' in str(ex.value)

    def test_sifir_otomatik_sozlesmesi_korunur(self):
        """0 = 'sen coz'. Bu sozlesme onarimla DEGISMEZ."""
        inj = self._enjektor(0)
        assert inj.showerhead_params['n_holes'] == 0
        sonuc = inj.calculate()
        assert sonuc['n_holes'] > 0

    @pytest.mark.parametrize('istenen,kenar', [(4, 'ust'), (400, 'alt')])
    def test_kirpma_gerekcesi_YANITTA_durur(self, istenen, kenar):
        """Kirpma olduysa gerekce ``warnings`` dizisinde de olmali.

        OLCULDU (taban ``7cd08bcc``): 4 delik istenince imalat bandi ust
        ucundan (2,00 mm) 9 delige, 400 delik istenince alt ucundan
        (0,30 mm) 362 delige cikiliyor; taban bunu YALNIZ
        ``warnings.warn`` ile sunucu gunlugune yaziyordu.

        ÖH D37 A2 hibrit · denetçi Ş2 (ana model kararı): 9 ve 362 ESKİ
        bandın (0,3/2,0 mm, kaynaksız) ÖLÇÜLMÜŞ sabitleriydi. Bant tek
        kaynaklı ``hrma.constants.ORIFICE_D_BAND_MM`` (0,5/2,5 mm; F-10)
        olunca teslim 6 × 2,50 ve 131 × 0,50 mm'ye döndü ve literal
        parametreler kırmızıya düştü. Testin NİYETİ bant sayısı değil:
        "kırpma olduysa gerekçe yanıtta durur" ve "kırpma doğru yöne
        yapılır". Beklenen teslim artık BANTTAN türetilir — aynı alan
        korunumu: A = ṁ/(C_d·√(2ρΔP)) (orifis denklemi, Sutton & Biblarz
        Böl. 8), kırpılan çap bandın ilgili KENARI, teslim = o çapta A'yı
        karşılayan EN KÜÇÜK n = ⌈A / (π·d_kenar²/4)⌉. Eski bantla
        (0,3/2,0) bu türetim 9 ve 362'yi AYNEN verir (ters mutasyonla
        ölçüldü: docs/scofield/raw/OH/A2/hibrit/a1/sart/).
        """
        from hrma.constants import ORIFICE_D_BAND_MM
        d_min_mm, d_max_mm = ORIFICE_D_BAND_MM
        inj = self._enjektor(istenen)
        sonuc = inj.calculate()
        # Aynı alan korunumu: hedef debinin istediği toplam orifis alanı [mm²]
        # (girdiler çözücünün kendi yayımladığı ṁ, C_d, ρ, ΔP).
        alan_mm2 = inj.mdot_ox / (
            inj.C_d * math.sqrt(2.0 * inj.rho_ox * inj.delta_P_inj * 1e5)
        ) * 1e6
        d_istenen_mm = 2.0 * math.sqrt(alan_mm2 / (istenen * math.pi))
        d_kenar_mm = d_max_mm if kenar == 'ust' else d_min_mm
        # Ön koşul: parametre hâlâ kırpma ÜRETİYOR mu? (Bant bir gün bu
        # isteği içine alacak kadar genişlerse test sessizce anlamsızlaşmaz,
        # adıyla kırmızı olur.)
        if kenar == 'ust':
            assert d_istenen_mm > d_max_mm, (
                f'{istenen} delik {d_istenen_mm:.4f} mm verir, bant üst ucu '
                f'{d_max_mm} mm: bu parametre artık kırpma üretmiyor')
        else:
            assert d_istenen_mm < d_min_mm, (
                f'{istenen} delik {d_istenen_mm:.4f} mm verir, bant alt ucu '
                f'{d_min_mm} mm: bu parametre artık kırpma üretmiyor')
        delik_alani_mm2 = math.pi * d_kenar_mm ** 2 / 4.0
        teslim = math.ceil(alan_mm2 / delik_alani_mm2)
        # Kırpma YÖNÜ: çap bandın doğru kenarına oturur, delik sayısı o yönde
        # değişir (üst kenar → daha çok delik, alt kenar → daha az delik).
        assert sonuc['hole_diameter'] == pytest.approx(d_kenar_mm, rel=1e-12)
        assert sonuc['n_holes'] == teslim
        assert (teslim > istenen) if kenar == 'ust' else (teslim < istenen)
        # Alan korunumu: teslim edilen plan hedef alanı karşılar ve bir delik
        # eksiği karşılamaz (en küçük n).
        assert teslim * delik_alani_mm2 >= alan_mm2
        assert (teslim - 1) * delik_alani_mm2 < alan_mm2
        kirpma_satiri = [u for u in (sonuc.get('warnings') or [])
                         if 'clamped to manufacturing band' in str(u)]
        assert kirpma_satiri, (
            f"delik sayisi {istenen} -> {sonuc['n_holes']} degisti ama "
            f"yanitta kirpma gerekcesi yok: {sonuc.get('warnings')}")
        assert f'requested hole count ({istenen})' in kirpma_satiri[0]
        assert 'was NOT' in kirpma_satiri[0]
        # Gerekçe KIRPILDIĞI bandın sayısını taşır (tek kaynak, iki uç).
        assert f'({d_min_mm:.2f}-{d_max_mm:.2f} mm)' in kirpma_satiri[0]
        assert f'adjusted to {teslim} ' in kirpma_satiri[0]

    def test_kirpma_yoksa_kayit_da_yok(self):
        inj = self._enjektor(40)
        sonuc = inj.calculate()
        assert sonuc['n_holes'] == 40
        assert not [u for u in (sonuc.get('warnings') or [])
                    if 'clamped to manufacturing band' in str(u)]


# =====================================================================
# P16B1-47 (CURUTULDU) — oxidizer_temp mutlak sifir alti
# =====================================================================
class TestP16B147OksitleyiciSicakligi:
    """Kalem '-50 K -> 200' diyor; olcum HTTP 400 gosterdi.

    ONCE (``a2/once.json`` K4, taban ``7cd08bcc``): ``oxidizer_temp = -50``
    -> HTTP 400, 292 bayt, gerekce "tank_temperature = -50.00 K is outside
    the saturated-liquid envelope of N2O ... (182.33 K < T < 309.52 K,
    NIST WebBook)"; ``1e9`` -> HTTP 400, 299 bayt (kritik sicaklik ustu).
    Yani hem alt hem UST imkansizlik kapali. Bekci kapanisi dondurur.
    """

    # ÖH D31 fix-34b — SÖZLEŞME DEĞİŞTİ, bekçi yeni sözleşmeyi okuyor.
    #
    # ÖLÇÜLDÜ (fix-34b, taban ``6acd6a48``): ``-50`` ve ``0`` artık zarf
    # kontrolünden ÖNCE merkezî pozitiflik kapısına takılıyor —
    # ``invalid_fields[].reason = 'not_positive'``, ``limits =
    # 'finite, > 0'``, ``details`` satırı "mutlak sıcaklık: 0 K altı
    # yoktur". Bu red DAHA TEMEL ve DAHA DOĞRUdur: sıfır ve negatif
    # mutlak sıcaklık N2O'nun zarfından bağımsız olarak yoktur, ve red
    # artık ALAN ADIYLA geliyor (eski zarf metni alanı adlandırmıyordu).
    # Kalemin iddiası AYNEN korunur: imkânsız sıcaklık REDDEDİLİR.
    #
    # Zarf kolu ÖLÜ BIRAKILMAZ: pozitif ama banda düşmeyen değerlerle
    # ayrıca sınanır (aşağıdaki ikinci düğüm), yoksa zarf kapısı bir gün
    # sökülse bu sınıf yeşil kalırdı.

    @pytest.mark.parametrize('T', [-50, 0])
    def test_mutlak_sifir_alti_sicaklik_ADIYLA_reddedilir(self, istemci, T):
        govde = dict(TABAN)
        govde['oxidizer_temp'] = T
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 400, r.get_data(as_text=True)[:200]
        govde_json = r.get_json()
        assert 'oxidizer_temp' in _alanlar(govde_json), (
            'red alan adını söylemiyor: %r' % (govde_json,))
        sebepler = {k.get('reason') for k in govde_json['invalid_fields']
                    if k.get('field') == 'oxidizer_temp'}
        assert sebepler == {'not_positive'}, (
            'redde makine-okur sebep yok: %r' % (sebepler,))
        metin = r.get_data(as_text=True)
        assert 'finite, > 0' in metin, (
            'kabul edilen bant künyesi yanıtta yok: %s' % metin[:300])

    @pytest.mark.parametrize('T', [50, 350, 1e9])
    def test_zarf_disi_pozitif_sicaklik_reddedilir(self, istemci, T):
        """Pozitif ama doymuş-sıvı zarfına düşmeyen sıcaklık da reddedilir.

        Bu düğüm zarf kapısını AYRI ölçer: alt (50 K), üst-kritik (350 K)
        ve uç (1e9 K) değerlerin üçü de 400 döner ve gerekçe zarfı ADIYLA
        söyler. Pozitiflik kapısı bu değerleri geçirir, yani iki kapı
        birbirini GİZLEMEZ.
        """
        govde = dict(TABAN)
        govde['oxidizer_temp'] = T
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 400, r.get_data(as_text=True)[:200]
        metin = r.get_data(as_text=True)
        assert 'saturated-liquid envelope' in metin or 'triple point' in metin, (
            'zarf reddi gerekçesiz: %s' % metin[:300])


# =====================================================================
# P16B1-48 (CURUTULDU) — gas_constant olu ama BEYANLI
# =====================================================================
class TestP16B148GazSabiti:
    """Kalem 'olu ve beyansiz' diyor; olcum BEYANI buldu.

    ONCE (``a2/once.json`` K5K6.gas_constant, taban ``7cd08bcc``):
    ``gas_constant = 250`` -> HTTP 200 ve 33 229 ortak sayisal yapragin
    0'i degisiyor (olu, DOGRU: R = R_evrensel/MW cozucunun ciktisi) AMA
    yanit ``inputs_not_used`` icinde ``{'field': 'gas_constant', 'reason':
    'solved_by_model', 'submitted': 250.0, 'used_by_model':
    325.5933453017038}`` tasiyor. ``-397`` -> HTTP 400, alan adiyla.
    """

    def test_negatif_gaz_sabiti_reddedilir(self, istemci):
        govde = dict(TABAN)
        govde['gas_constant'] = -397
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 400
        assert 'gas_constant' in _alanlar(r.get_json())

    def test_cozucu_sahipli_alanlar_beyan_listesindedir(self):
        from hrma import app as app_modulu
        assert 'gas_constant' in app_modulu._CALCULATE_SOLVER_OWNED_FIELDS
        assert 'chamber_temperature' in (
            app_modulu._CALCULATE_SOLVER_OWNED_FIELDS)


# =====================================================================
# P16B1-51 (ONARILDI) — tasarim emniyet katsayisi kapisi
# =====================================================================
class TestP16B151EmniyetKatsayisi:
    """ONCE (``a2/once.json`` K5K6.safety_factor, taban ``7cd08bcc``;
    33 187 ortak sayisal yaprak):

        safety_factor = 6,0   -> HTTP 200, 9 324 yaprak degisiyor (CANLI)
        safety_factor = 0     -> HTTP 200, 0 yaprak, inputs_not_used YOK
        safety_factor = -2,5  -> HTTP 200, 0 yaprak, inputs_not_used YOK
        safety_factor = NaN   -> HTTP 200, 0 yaprak, inputs_not_used YOK

    ve ``design_safety_factor`` yapragi hicbir kosuda yok. Yani urundeki
    en dogrudan guvenlik girdisi sessizce dusuyordu.
    """

    @pytest.mark.parametrize('deger,gerekce', [
        (0, 'outside_accepted_range'),
        (-2.5, 'outside_accepted_range'),
        (1e9, 'outside_accepted_range'),
        (1.0, 'outside_accepted_range'),
        (float('nan'), 'not_finite'),
        (float('inf'), 'not_finite'),
        ('cok', 'not_a_number'),
        (True, 'not_a_number'),
    ])
    def test_imkansiz_hedef_reddedilir(self, istemci, deger, gerekce):
        govde = dict(TABAN)
        govde['safety_factor'] = deger
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert _alanlar(g) == ['safety_factor']
        kayit = [k for k in g['invalid_fields']
                 if k['field'] == 'safety_factor'][0]
        assert kayit['reason'] == gerekce
        assert kayit['accepted_range'] == [SAFETY_FACTOR_MIN,
                                           SAFETY_FACTOR_MAX]

    def test_bant_TEK_KAYNAKTAN_okunur(self):
        """Uc kapisi kendi sayisini yazmaz; motorun sabitini okur."""
        from hrma import app as app_modulu
        assert app_modulu.HYBRID_SAFETY_FACTOR_MIN is SAFETY_FACTOR_MIN
        assert app_modulu.HYBRID_SAFETY_FACTOR_MAX is SAFETY_FACTOR_MAX

    @pytest.mark.parametrize('deger', [None, ''])
    def test_vermedim_yolu_BIT_AYNI(self, istemci, deger):
        """None/'' 'vermedim' demektir; o yol kapidan gecmez."""
        govde = dict(TABAN)
        govde['safety_factor'] = deger
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 200, r.get_data(as_text=True)[:200]


# =====================================================================
# P16B2-09 (CURUTULDU) — chamber_temperature kati/sivida BEYANLI olu
# =====================================================================
class TestP16B209OdaSicakligiBeyani:
    """Kalem 'unwired_inputs listelerinde de yok' diyor; olcum beyani buldu.

    ONCE (``a2/once.json`` K7, taban ``7cd08bcc``):
    ``/calculate_solid`` ve ``/calculate_liquid``, ``chamber_temperature``
    -1e9 / 1e9 / 3500 icin 0/3 595 (kati) ve 0/2 892 (sivi) yaprak
    degistiriyor (OLU, dogru: T_c yakit kaydindan gelen bir CIKTIDIR) ama
    yanit ``inputs_not_used`` icinde ``{'field': 'chamber_temperature',
    'reason': 'solver_owned_output_name', 'use_instead': 'flame_temp',
    'used_by_model': 3614.8}`` tasiyor. Z5S / S5 hukmu (OLU ILANI)
    uygulanmis durumda; bekci onu dondurur.
    """

    @pytest.mark.parametrize('yol,govde', [('/calculate_solid', KATI),
                                           ('/calculate_liquid', SIVI)])
    def test_oda_sicakligi_beyanla_dusuyor(self, istemci, yol, govde):
        istek = dict(govde)
        istek['chamber_temperature'] = 3500
        r = istemci.post(yol, json=istek)
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        kayitlar = [k for blok in _yaprak_ara(r.get_json(), 'inputs_not_used')
                    for k in (blok or [])
                    if isinstance(k, dict)
                    and k.get('field') == 'chamber_temperature']
        assert kayitlar, 'chamber_temperature beyani yok'
        assert kayitlar[0]['reason'] == 'solver_owned_output_name'
        assert kayitlar[0]['submitted'] == 3500
        assert kayitlar[0]['used_by_model'] != 3500


# =====================================================================
# P16B3-20 (ONARILDI) — wall-profile istasyon sayisi
# =====================================================================
class TestP16B320IstasyonSayisi:
    """ONCE (``a2/once.json`` K8, taban ``7cd08bcc``):

        n_stations = 0   -> HTTP 200, 4 866 bayt, wall_profile.n_stations 5
        n_stations = -5  -> HTTP 200, 4 866 bayt, n_stations 5
        n_stations = 3   -> HTTP 200, 4 866 bayt, n_stations 5
        n_stations = 300 -> HTTP 200, 48 604 bayt, n_stations 300

    Uc ayri niyet BIT-AYNI yanita cokuyordu ve ``clamped`` diye bir yaprak
    yoktu; kirpmanin gerceklestigi hicbir yerden okunamiyordu.
    """

    @pytest.mark.parametrize('n', [0, -5, 3, 401, 1000000000])
    def test_bant_disi_istasyon_sayisi_reddedilir(self, istemci, n):
        govde = dict(WALL)
        govde['n_stations'] = n
        r = istemci.post('/api/analysis/wall-profile', json=govde)
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        g = r.get_json()
        assert g['error'] == 'n_stations_out_of_range'
        kayit = g['invalid_fields'][0]
        assert kayit['field'] == 'n_stations'
        assert kayit['accepted_range'] == [
            HeatTransferAnalyzer.N_STATIONS_MIN,
            HeatTransferAnalyzer.N_STATIONS_MAX]

    @pytest.mark.parametrize('n', [5, 40, 300, 400])
    def test_bant_ici_istasyon_sayisi_TESLIM_EDILIR(self, istemci, n):
        govde = dict(WALL)
        govde['n_stations'] = n
        r = istemci.post('/api/analysis/wall-profile', json=govde)
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['wall_profile']['n_stations'] == n

    def test_alan_gonderilmezse_yol_bit_ayni(self, istemci):
        r = istemci.post('/api/analysis/wall-profile', json=dict(WALL))
        assert r.status_code == 200
        assert r.get_json()['wall_profile']['n_stations'] == 40

    def test_bant_TEK_KAYNAKTAN_okunur(self):
        """Uc kapisi 5/400'u KOPYALAMAZ; modulun sabitini okur."""
        import inspect
        from hrma.analysis import heat_transfer_analysis as hta
        kaynak = inspect.getsource(hta.HeatTransferAnalyzer
                                   .analyze_axial_profile)
        assert 'self.N_STATIONS_MIN' in kaynak
        assert 'self.N_STATIONS_MAX' in kaynak
        assert 'max(5, min(' not in kaynak


# =====================================================================
# P16B3-21 (ONARILDI) — FEA mesh cozunurlugu
# =====================================================================
class TestP16B321MeshCozunurlugu:
    """ONCE (``a2/once2.json`` K9b, taban ``7cd08bcc``; ``max_rounds=0``):

        n_axial0 = 1e9   -> HTTP 200, fea.limits.n_axial0 = 256,
                            fea.limits.clamped = FALSE (199 304 bayt)
        n_axial0 = 0     -> HTTP 200, n_axial0 = 4,  clamped = FALSE
        n_axial0 = -4    -> HTTP 200, n_axial0 = 4,  clamped = FALSE
        n_axial0 = true  -> HTTP 200, n_axial0 = 4,  clamped = FALSE
        n_axial0 = 'abc' -> HTTP 200, n_axial0 = 16 (varsayilan), FALSE

    Mesh sessizce kirpiliyordu ve yanitin KENDI ``clamped`` bayragi
    "kirpilmadi" diyordu (o bayrak yalniz tur sayisini izliyordu).
    """

    MOTOR = {'motor_type': 'hybrid'}

    @pytest.mark.parametrize('yol,alan', [
        ('/api/fea/structural', 'n_axial0'),
        ('/api/fea/structural', 'n_radial0'),
    ])
    @pytest.mark.parametrize('deger,gerekce', [
        (0, 'must_be_positive'),
        (-4, 'must_be_positive'),
        ('abc', 'not_a_number'),
        (True, 'not_a_number'),
        (1.5, 'must_be_whole_number'),
        (float('nan'), 'not_finite'),
    ])
    def test_imkansiz_cozunurluk_reddedilir(self, istemci, yol, alan,
                                            deger, gerekce):
        govde = {'motor': self.MOTOR, 'max_rounds': 0, alan: deger}
        r = istemci.post(yol, json=govde)
        assert r.status_code == 422, r.get_data(as_text=True)[:250]
        g = r.get_json()
        assert g['error'] == 'invalid_mesh_resolution'
        assert g['invalid_fields'][0]['field'] == alan
        assert g['invalid_fields'][0]['reason'] == gerekce

    def test_butce_kirpmasi_BEYAN_EDILIR(self, istemci):
        r = istemci.post('/api/fea/structural',
                         json={'motor': self.MOTOR, 'max_rounds': 0,
                               'n_axial0': 1000000000})
        assert r.status_code == 200
        lim = r.get_json()['fea']['limits']
        assert lim['n_axial0'] == 256
        assert lim['clamped'] is True, 'kirpma olduysa bayrak TRUE olmali'
        kayit = [k for k in lim['mesh_clamped']
                 if k['field'] == 'n_axial0']
        assert kayit, lim['mesh_clamped']
        assert kayit[0]['requested'] == 1000000000
        assert kayit[0]['delivered'] == 256
        assert kayit[0]['accepted_range'] == [4, 256]

    def test_bant_icinde_kirpma_kaydi_YOK(self, istemci):
        r = istemci.post('/api/fea/structural',
                         json={'motor': self.MOTOR, 'max_rounds': 0,
                               'n_axial0': 24})
        assert r.status_code == 200
        lim = r.get_json()['fea']['limits']
        assert lim['n_axial0'] == 24
        assert lim['mesh_clamped'] == []
        assert lim['clamped'] is False

    def test_planar_uc_AYNI_tek_kaynagi_kullanir(self):
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu.api_fea_planar_grain)
        assert '_fea_mesh_int' in kaynak
        assert 'def _pozitif_int' not in kaynak
        kaynak2 = inspect.getsource(app_modulu.api_fea_structural)
        assert '_fea_mesh_int' in kaynak2
        assert 'def _pozitif_int' not in kaynak2


# =====================================================================
# P16B3-23 (ONARILDI) — termal FEA ortam sicakligi kapisi
# =====================================================================
class TestP16B323OrtamSicakligi:
    """ONCE (``a2/kapi_ast.json``, taban ``7cd08bcc``): ``/api/fea/thermal``
    govdesinde ``ambient_temperature_K`` ham ``data.get`` ile IKI yerde
    okunuyor (kopru cagrisi + ``scalars`` blogu) ve o alana uygulanan
    denetim cagrisi sayisi SIFIR. Yani -300 K (mutlak sifirin alti) ve
    "NaN" cozucuye AYNEN geciyor, sonra yanitta "ortam sicakligi buydu"
    diye yayimlaniyordu. Uc, kardeslerinin aksine
    (``_THERMAL_SAFETY_POSITIVE_FIELDS``) kapisiz calisiyordu.
    """

    MOTOR = {'motor_type': 'hybrid'}

    @pytest.mark.parametrize('deger,gerekce', [
        (-300, 'must_be_positive'),
        (0, 'must_be_positive'),
        ('NaN', 'not_finite'),
        (float('nan'), 'not_finite'),
        (float('-inf'), 'not_finite'),
        (True, 'not_a_number'),
        ('soguk', 'not_a_number'),
    ])
    def test_imkansiz_ortam_sicakligi_reddedilir(self, istemci, deger,
                                                 gerekce):
        r = istemci.post('/api/fea/thermal',
                         json={'motor': self.MOTOR,
                               'ambient_temperature_K': deger})
        assert r.status_code == 422, r.get_data(as_text=True)[:250]
        g = r.get_json()
        assert g['error'] == 'invalid_ambient_temperature'
        assert g['invalid_fields'][0]['field'] == 'ambient_temperature_K'
        assert g['invalid_fields'][0]['reason'] == gerekce

    def test_gecerli_sicaklik_kapiyi_gecer(self, istemci):
        """300 K kapiya takilmaz; kopru kendi hukmunu verir."""
        r = istemci.post('/api/fea/thermal',
                         json={'motor': self.MOTOR,
                               'ambient_temperature_K': 300})
        assert (r.get_json() or {}).get('error') != (
            'invalid_ambient_temperature')

    def test_motor_eksigi_SIRAYI_bozmaz(self, istemci):
        """Motor sonucu hic yoksa hukum yine 400 ``missing_motor_results``."""
        r = istemci.post('/api/fea/thermal',
                         json={'ambient_temperature_K': -300})
        assert r.status_code == 400
        assert r.get_json()['error'] == 'missing_motor_results'


# =====================================================================
# P16B3-24 (KISMEN) — TNT tablosu htpb tasimiyor
# =====================================================================
class TestP16B324TntTablosuKapsami:
    """BORC ODENDI — OH-D28-08 (OH D29 / yapisal-sistem a1).

    D28'de bu sinif OLCULEN KUSURU donduruyordu ve "yari kapandiginda
    KIRMIZI verir" diye yaziliydi. Kapandi: kirmizi verdi, cevrildi.

    ONCE (taban ``4dc63c11``, ``D29/yapisal-sistem/a1/once.json``):

        propellant_type='htpb'  -> sinif liquid_biprop, faktor 0,35,
                                   TNT 1,75 kg, oldurucu 3,313262612359215 m
        liquid_biprop+'liquid'  -> AYNI uc sayi (hibrit ile LOX/RP-1 sivi
                                   cift-iticisi ayirt edilemiyordu)

    SONRA (``sonra.json``): hibritin TNT esdegeri artik SIVI tablosundan
    ODUNC ALINMIYOR, oksitleyicinin ayrisma entalpisinden TURETILIYOR
    (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, Denk. 2):

        htpb -> sinif hybrid_n2o, faktor 0,4455501783563947,
                TNT 2,2277508917819735 kg, oldurucu 3,590862032111756 m

    'htpb' hala bir TABLO ANAHTARI DEGILDIR ve olmamalidir: HTPB bir
    YAKITTIR, itici SISTEMI degil; ayni grain LOX ile bambaska bir
    esdegere sahiptir. Kalemin 'tabloda bulamiyor' yarisi bu yuzden
    "tabloya htpb ekle" diye degil "hibritin kendi sinifini kur" diye
    odendi. Ayrinti: ``docs/scofield/raw/OH/D29/yapisal-sistem/a1/rapor.md``.
    """

    def test_htpb_bir_YAKIT_adidir_sinif_anahtari_DEGIL(self):
        """Tablo anahtarlari itici SINIFIDIR; yakit adi anahtar olmaz."""
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        tablo = SafetyAnalyzer().propellant_tnt_equivalents
        assert 'htpb' not in tablo
        # ...ama hibritin ARTIK kendi sinifi var (D28'de yoktu).
        assert 'hybrid_n2o' in tablo, (
            'OH-D28-08 onarimi geri alinmis: hibrit sinifi yok')

    def test_hibrit_artik_SIVI_cift_iticinin_sayisini_ODUNC_ALMIYOR(
            self, istemci):
        """D28'in dondurdugu esitlik KIRILDI — kalemin asil kusuru buydu."""
        olculen = {}
        for etiket, yama in (
                ('htpb', {'propellant_type': 'htpb'}),
                ('sivi', {'propellant_type': 'liquid_biprop',
                          'motor_type': 'liquid'})):
            govde = dict(GUVENLIK)
            govde.update(yama)
            r = istemci.post('/analyze_safety', json=govde)
            assert r.status_code == 200
            g = r.get_json()
            olculen[etiket] = (_yaprak_ara(g, 'tnt_equivalent_kg')[0],
                               _yaprak_ara(g, 'explosive_class')[0])
        assert olculen['sivi'][0] == pytest.approx(1.75), (
            'sivi kol DEGISMEMELIYDI')
        assert olculen['htpb'][0] != olculen['sivi'][0], (
            'hibrit hala sivi cift-iticinin TNT sayisini kullaniyor')
        assert olculen['htpb'][0] == pytest.approx(2.2277508917819735)
        assert olculen['htpb'][1] == 'hybrid_n2o'
        assert olculen['sivi'][1] == 'liquid_biprop'

    def test_kunye_YAYIMLANIYOR_ve_durust(self, istemci):
        """Kunye hala yayimlaniyor; artik kaynagi da tasiyor."""
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'htpb'
        r = istemci.post('/analyze_safety', json=govde)
        kunye = _yaprak_ara(r.get_json(), 'explosive_class_basis')
        assert kunye, 'sinif cozumunun gerekcesi yayimlanmiyor'
        metin = kunye[0]
        assert 'is not a tabulated class' in metin
        assert "motor_type 'hybrid'" in metin
        # D29: yakitin ATIL oldugu ve sayinin nereden geldigi de yazili.
        assert 'inert polymer' in metin
        assert 'ASSUMPTION' in metin


def test_kanit_dosyalari_yerinde():
    """Olcum kaniti depoda durur (rapor iddiasi dosyayla eslesir)."""
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[1]
    dizin = kok / 'docs/scofield/raw/OH/D28/app-api/a2'
    for ad in ('olcum.py', 'once.json', 'olcum2.py', 'once2.json',
               'rapor.md'):
        assert (kanit_gerekli(dizin / ad)).exists(), ad
    once = json.loads((kanit_gerekli(dizin / 'once.json')).read_text(encoding='utf-8'))
    # Kalem hukumleri ONCE olcumunden dogar; dosya bozulursa bekci yakalar.
    assert once['K1_P16B1-35']['kediler']['http'] == 422
    assert once['K5K6']['safety_factor']['sifir']['yaprak']['degisen'] == 0
    assert once['K8_P16B3-20']['uc']['n_stations_yayin'] == 5
    assert math.isclose(
        once['K5K6']['gas_constant']['250']['inputs_not_used'][0][0][
            'used_by_model'], 325.5933453017038)
