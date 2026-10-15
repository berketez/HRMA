# -*- coding: utf-8 -*-
"""ÖH Dalga-26 / app-api aşama-4 — P07 havuzunun 11 kalemi.

Her kalem için BİR bekçi: kusuru gören (ters-mutasyonla kanıtlı) ya da —
kalem ölçümle çürütüldüyse — çürütmenin geri gelmesini gören.

Ölçüm: ``docs/scofield/raw/OH/D26/app-api/a4/once.json`` (onarımdan önce),
``sonra.json`` (sonra). Kalem sınıfının tamamı savcıda ``test-yok``tur
(``docs/scofield/raw/P07/S1-savci.md`` EK A) — yani onbirinin de asıl
borcu bekçinin KENDİSİDİR.
"""
import contextlib
import io
import json

import pytest

from hrma.app import (CACHED_FUEL_PROPERTIES, FLOW_ANALYSIS_DEFAULTS,
                      _CIDAR_TAKMA_ADLARI, app)


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(client, yol, yuk):
    """Uç günlüğe basıyor; çıktı testin okunurluğunu bozmasın."""
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return client.post(yol, json=yuk)


OPT = {'fuel': 'htpb', 'oxidizer': 'n2o'}
HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}
TERMAL = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
          'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
          'mdot_total': 1.0, 'wall_thickness': 0.003}
YORUNGE = {'thrust': 1000.0, 'burn_time': 10.0, 'initial_mass': 50.0,
           'final_mass': 25.0, 'drag_coefficient': 0.5,
           'reference_area': 0.1}


# ---------------------------------------------------------------------------
# P7B3-12 — /api/find-optimum-of BOŞ gövdeden "optimum" (ÇÜRÜTÜLDÜ)
# ---------------------------------------------------------------------------
class TestP7B312OptimumBosGovde:
    """Kalem başlığı ÖLÇÜMLE çürütüldü; bekçi çürütmeyi kilitler.

    Ölçüldü (``a4/once.json`` K1, bu worktree): boş gövde HTTP **422** +
    ``missing_propellant_pair`` alıyor ve ``optimum_of_ratio`` yaprağı
    gövdenin hiçbir yerinde geçmiyor. Kalemin ölçtüğü davranış (HTTP 200 +
    O/F 6,845 + Isp 232,72 s) D21/P16B1-16 onarımıyla kalkmış. Bekçi
    yoktu (savcı: ``test-yok``) — geri gelirse bu test görür.
    """

    def test_bos_govde_optimum_YAYIMLAMAZ(self, client):
        r = _post(client, '/api/find-optimum-of', {})
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        assert govde['error_code'] == 'missing_propellant_pair'
        assert set(govde['missing_fields']) == {'fuel', 'oxidizer'}
        ham = json.dumps(govde, ensure_ascii=False)
        assert 'optimum_of_ratio' not in ham, (
            'itici çifti verilmeden "optimum O/F" hükmü yayımlandı')
        assert 'max_isp' not in ham

    def test_saglikli_cift_HALA_optimum_uretiyor(self, client):
        """Kapı meşru yolu kesmiyor (çürütme, kapının fazlalığı değil)."""
        r = _post(client, '/api/find-optimum-of', dict(OPT))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert r.get_json()['optimum_of_ratio'] > 0


# ---------------------------------------------------------------------------
# P7B3-13 — /api/find-optimum-of üst fizik kapısı (ÇÜRÜTÜLDÜ)
# ---------------------------------------------------------------------------
class TestP7B313OptimumBasincKapisi:
    """Ölçüldü (``a4/once.json`` K2): 1e9 · 1e12 · 2e6 bar ve 0 · 'abc'
    BEŞİ DE HTTP 422 ``invalid_chamber_pressure``. Kalemin ölçtüğü iki
    davranış (imkânsız basınçta Isp hükmü; P=0 / P='abc' -> HTTP 500)
    D21/P16B1-17 ile kalkmış.
    """

    @pytest.mark.parametrize('pc', [1e9, 1e12, 2e6])
    def test_imkansiz_basincta_isp_HUKMU_YOK(self, client, pc):
        r = _post(client, '/api/find-optimum-of', dict(OPT,
                                                       chamber_pressure=pc))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        assert r.get_json()['error_code'] == 'invalid_chamber_pressure'
        assert 'max_isp' not in json.dumps(r.get_json(), ensure_ascii=False)

    @pytest.mark.parametrize('pc', [0, 'abc'])
    def test_bozuk_basinc_500_URETMEZ(self, client, pc):
        """İstemci hatası SUNUCU arızası gibi yayımlanamaz."""
        r = _post(client, '/api/find-optimum-of', dict(OPT,
                                                       chamber_pressure=pc))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        assert r.get_json()['error_code'] == 'invalid_chamber_pressure'


# ---------------------------------------------------------------------------
# P7B3-19 — /api/trajectory-analysis ham 500 + Türkçe istisna (ÇÜRÜTÜLDÜ)
# ---------------------------------------------------------------------------
TR_HARF = set('çğıöşüÇĞİÖŞÜ')


class TestP7B319YorungeIstemciHatasi:
    """Ölçüldü (``a4/once.json`` K3): yedi istemci-hatası gövdesinin
    YEDİSİ de HTTP **422** + ``invalid_trajectory_input`` +
    ``invalid_fields`` alıyor; hiçbirinde Türkçe harf (yani ham modül
    istisnası) yok. Kalemin ölçtüğü "HTTP 500 + ham Türkçe metin + iç
    değişken adı sızıntısı" kalkmış.
    """

    @pytest.mark.parametrize('ek', [
        {'final_mass': 90.0}, {'initial_mass': 0.0}, {'initial_mass': -5.0},
        {'reference_area': -1.0}, {'drag_coefficient': -2.0},
        {'burn_time': 0.0}, {'thrust': -100.0},
    ])
    def test_istemci_hatasi_500_DEGIL_422(self, client, ek):
        r = _post(client, '/api/trajectory-analysis', dict(YORUNGE, **ek))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        assert govde['error'] == 'invalid_trajectory_input'
        assert govde['invalid_fields'], 'hangi alanın bozuk olduğu yok'
        assert all('field' in k for k in govde['invalid_fields'])

    @pytest.mark.parametrize('ek', [
        {'final_mass': 90.0}, {'reference_area': -1.0}, {'burn_time': 0.0},
    ])
    def test_govdede_ham_TURKCE_istisna_metni_yok(self, client, ek):
        r = _post(client, '/api/trajectory-analysis', dict(YORUNGE, **ek))
        metin = r.get_data(as_text=True)
        sizan = sorted(TR_HARF.intersection(metin))
        assert not sizan, (
            'yanıtta Türkçe harf var — modülün ham istisna metni '
            'kullanıcıya sızıyor: %r' % sizan)


# ---------------------------------------------------------------------------
# P7B3-24 — cidar anahtarı köprüsü tek adlı (ONARILDI)
# ---------------------------------------------------------------------------
class TestP7B324CidarTakmaAdi:
    """Ölçüldü (``a4/once.json`` K4): ``wall_thickness = 20`` ->
    ``user_supplied`` / 20,0 mm; ``wall_thickness_mm``, ``t_wall``,
    ``chamber_wall_thickness``, ``case_thickness`` -> DÖRDÜ DE
    ``sized_by_hrma`` / 9,3678 mm ve yanıt *"No wall thickness was
    supplied"* diyordu. Kullanıcı cidarını GÖNDERMİŞKEN.
    """

    @pytest.mark.parametrize('ad', list(_CIDAR_TAKMA_ADLARI))
    def test_takma_ad_SESSIZCE_dusmez(self, client, ad):
        r = _post(client, '/calculate', dict(HIBRIT, **{ad: 20.0}))
        assert r.status_code == 422, (
            '%s sessizce düştü ve HRMA kendi cidarını boyutlandırdı '
            '(HTTP %s)' % (ad, r.status_code))
        govde = r.get_json()
        assert govde['error'] == 'unrecognised_wall_thickness_field'
        alanlar = [k['field'] for k in govde['invalid_fields']]
        assert ad in alanlar
        assert govde['invalid_fields'][0]['canonical_field'] == \
            'wall_thickness'

    def test_kanonik_ad_HALA_kabul(self, client):
        """Sağlıklı yol bit-aynı: kanonik ad kapıdan geçer."""
        r = _post(client, '/calculate', dict(HIBRIT, wall_thickness=20.0))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        yapisal = r.get_json()['motor']['structural_analysis']
        assert yapisal['chamber_analysis']['wall_thickness_source'] == \
            'user_supplied'

    def test_takma_ad_listesi_TEK_KAYNAK(self):
        """Kapı ile bekçi aynı sabitten okur (ÖK-04)."""
        assert 'wall_thickness' not in _CIDAR_TAKMA_ADLARI
        assert len(set(_CIDAR_TAKMA_ADLARI)) == len(_CIDAR_TAKMA_ADLARI)


# ---------------------------------------------------------------------------
# P7B3-26 — /analyze_thermal_safety üst fizik kapısı (ÇÜRÜTÜLDÜ)
# ---------------------------------------------------------------------------
class TestP7B326TermalUstKapi:
    """Ölçüldü (``a4/once.json`` K5): kalemin saydığı ÜÇ girdinin ÜÇÜ de
    HTTP **422** alıyor (P16S1-01 onarımı). ``mdot_total`` üst ucu hâlâ
    açık ama ORASI BU KALEMİN DEĞİL: ``_ust_sinir_bandi`` künyesi
    ``mdot_total``ı adıyla dışarıda bırakıyor ("tabloda karşılığı olmayan
    alana DOKUNULMAZ — Berke kararı"). Bekçi o kapıyı DAYATMAZ, yalnız
    kanonik bandı olan üç alanı korur.
    """

    @pytest.mark.parametrize('ek,alan', [
        ({'chamber_temperature': 100000.0}, 'chamber_temperature'),
        ({'chamber_pressure': 1e7}, 'chamber_pressure'),
        ({'chamber_length': 1e9}, 'chamber_length'),
    ])
    def test_bant_disi_deger_HUKUM_URETMEZ(self, client, ek, alan):
        r = _post(client, '/analyze_thermal_safety', dict(TERMAL, **ek))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        assert govde['error'] == 'invalid_thermal_input'
        bozuk = [k['field'] for k in govde['invalid_fields']]
        assert alan in bozuk
        assert 'risk_level' not in json.dumps(govde, ensure_ascii=False)

    def test_cok_kucuk_capta_hukum_yok(self, client):
        r = _post(client, '/analyze_thermal_safety',
                  dict(TERMAL, chamber_diameter=1e-9))
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# P7B3-31 — /api/analysis/wall-profile birim ve dayanak beyanı (ONARILDI)
# ---------------------------------------------------------------------------
class TestP7B331CidarProfiliDayanak:
    """Ölçüldü (``a4/once.json`` K6): 18 sütunlu yanıtta ``units`` /
    ``q_basis`` / ``T_wall_eq_basis`` / ``column_basis`` dizgelerinin
    DÖRDÜ DE 0 kez geçiyordu. Orta istasyonda
    q/(T_rec − T_wall_eq) = 350.506,8 W/(m²·K), yayımlanan ``h_g``nin
    (4.069,4) **86,1 KATI** — yani sütunlar kardeş dizi DEĞİL.
    """

    @pytest.fixture(scope='class')
    def profil(self, client):
        r = _post(client, '/api/analysis/wall-profile', dict(TERMAL))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()['wall_profile']

    def test_her_sayisal_sutunun_birimi_var(self, profil):
        birim = profil.get('units')
        assert birim, 'birim beyanı yok'
        for ad in ('x_mm', 'r_mm', 'h_g', 'q_MW', 'T_recovery', 'T_wall_eq',
                   'mach', 'area_ratio', 'throat_diameter_m'):
            assert ad in birim, '%s sütununun birimi beyan edilmemiş' % ad
        assert birim['q_MW'] == 'MW/m^2'
        assert birim['h_g'] == 'W/(m^2 K)'
        assert birim['T_wall_eq'] == 'K'

    def test_q_ve_T_wall_eq_KARDES_DIZI_DEGIL_diyor(self, profil):
        dayanak = profil.get('column_basis')
        assert dayanak, 'sütun dayanağı yok'
        q = dayanak['q_MW']
        assert 'T_wall_eq' in q and 'NOT' in q, (
            'q_MW ile T_wall_eq arasındaki ilişki beyan edilmemiş')
        assert 'Tw_ref' in q or 'reference' in q.lower()
        assert 'Tw_ref' in dayanak['h_g'] or 'reference' in \
            dayanak['h_g'].lower()

    def test_olculen_86_kat_ayrisma_HALA_gecerli(self, profil):
        """Beyanın DOĞRU olduğunu ölçümle sınar (totolojik bekçi değil)."""
        i = len(profil['q_MW']) // 2
        h_turetilen = (profil['q_MW'][i] * 1e6) / (
            profil['T_recovery'][i] - profil['T_wall_eq'][i])
        oran = h_turetilen / profil['h_g'][i]
        assert oran > 10.0, (
            'q ile T_wall_eq artık aynı enerji dengesini kapatıyorsa '
            'column_basis cümlesi bayatlamıştır: oran %.3f' % oran)


# ---------------------------------------------------------------------------
# P7B4-01 — /api/get-fuel-properties uydurma yoğunluk (ONARILDI)
# ---------------------------------------------------------------------------
#: Literatür yoğunlukları [kg/m³] — kalemin kendi ölçüm satırından.
GERCEK_YOGUNLUK = {'lh2': 70.85, 'methane': 422.6, 'rp1': 810.0}


class TestP7B401UydurmaYogunluk:
    """Ölçüldü (``a4/once.json`` K7): alan ``molecular_weight`` (gaz) ya da
    ``molecular_weight * 10`` (sıvı) basıyordu ve gövde onu
    ``source = 'NASA CEA Database'`` künyesiyle yayımlıyordu::

        LH2     2,016  (gerçek 70,85  -> 35,1 kat küçük)
        HTPB   54,09   (920           -> 17,0 kat)
        metan  16,043  (422,6         -> 26,3 kat)
        RP-1 1673,1    (810           ->  2,07 kat büyük)
    """

    @pytest.mark.parametrize('yakit', sorted(GERCEK_YOGUNLUK))
    def test_yogunluk_MOLEKUL_AGIRLIGI_DEGIL(self, client, yakit):
        r = _post(client, '/api/get-fuel-properties', {'fuel_type': yakit})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        oz = r.get_json()['properties']
        yog, mw = oz['density'], oz['molecular_weight']
        assert yog is not None
        # Molekül ağırlığının kendisi ya da 10 katı OLAMAZ.
        assert abs(yog - mw) > 1e-6, (
            '%s: yoğunluk hâlâ molekül ağırlığı (%r)' % (yakit, yog))
        assert abs(yog - mw * 10.0) > 1e-6, (
            '%s: yoğunluk hâlâ MW*10 (%r)' % (yakit, yog))
        # Ve literatüre yakın (bant: %5).
        bagil = abs(yog - GERCEK_YOGUNLUK[yakit]) / GERCEK_YOGUNLUK[yakit]
        assert bagil < 0.05, (
            '%s: yayımlanan %r, literatür %r (bağıl fark %.3f)'
            % (yakit, yog, GERCEK_YOGUNLUK[yakit], bagil))
        assert oz['density_source'], 'yoğunluğun kökeni söylenmiyor'
        assert oz['density_unit'] == 'kg/m^3'

    def test_kaydi_olmayan_yakitta_SAYI_UYDURULMAZ(self, client):
        """Kaydı olmayan yakıtta alan null + gerekçe.

        ÖH D27 / app-api a3 (OH-D26-17) — ÖRNEK YAKIT DEĞİŞTİ, İDDİA AYNI.
        Bu test HTPB'yi "kaydı olmayan yakıt" örneği olarak kullanıyordu ve
        ``assert 'htpb' not in CACHED_FUEL_PROPERTIES`` ile o BOŞLUĞU
        DONDURUYORDU. OH-D26-17 tam da o boşluğu kapattı: HTPB artık
        literatür künyeli (920 kg/m³, Chiaverini & Kuo) bir kayda sahip.
        İddia ("kaydı olmayan yakıta sayı uydurulmaz") aynen korundu ve
        bugün gerçekten kaydı olmayan bir yakıta taşındı (``paraffin``).
        HTPB'nin kaydının VARLIĞI ayrıca sınanıyor:
        ``test_d27_app_api_a3.py::TestOHD2617KunyeliKayit``.
        """
        assert 'paraffin' not in CACHED_FUEL_PROPERTIES
        r = _post(client, '/api/get-fuel-properties',
                  {'fuel_type': 'paraffin'})
        oz = r.get_json()['properties']
        assert oz['density'] is None, (
            'kaydı olmayan yakıta yoğunluk uyduruldu: %r' % oz['density'])
        assert oz['density_unavailable_reason'] == \
            'no_measured_density_record_for_this_fuel'
        assert 'molecular weight' in oz['density_basis']

    def test_NASA_CEA_kunyesi_yalnız_NASA_kaydinda(self, client):
        """``properties.source = 'Custom'`` iken üst künye "NASA CEA"
        diyemez (kalemin ikinci ayağı: aynı gövdede iki köken)."""
        r = _post(client, '/api/get-fuel-properties', {'fuel_type': 'rp1'})
        govde = r.get_json()
        tur_kaynagi = govde['properties']['source']
        if not str(tur_kaynagi).upper().startswith('NASA'):
            assert govde['source'] != 'NASA CEA Database', (
                'tür kaydı %r iken yanıt "NASA CEA Database" diyor'
                % tur_kaynagi)
            assert govde['species_source'] == tur_kaynagi


# ---------------------------------------------------------------------------
# P7B4-02 — tanınmayan yakıt sessizce RP-1'e (KISMEN: sessizlik kalktı)
# ---------------------------------------------------------------------------
class TestP7B402TaninmayanYakit:
    """Ölçüldü (``a4/once.json`` K8): ``substituted_record`` ve
    ``substituted_basis`` ZATEN vardı (Z5S/S6), yani "sessizce" iddiası
    çürük. Ayakta kalan yarı üst düzey ``note`` idi: yalnız "not found ...
    using cached data" diyordu, YERİNE NE KONDUĞUNU söylemiyordu.
    """

    # ÖH D27 / app-api a3 (P7B4-02) — YÖNÜ DÖNDÜ, GEREKÇE: bu bekçi
    # ikamenin ADIYLA SÖYLENMESİNİ istiyordu ve böylece ikamenin KENDİSİNİ
    # (HTTP 200 + RP-1'in sayıları) kilitliyordu. Beyan geldi ve ölçüldü;
    # ama beyan çözüm değildir (Doktrin 1). Uç artık ikame etmiyor: adlı
    # 422. İddianın çekirdeği ("kullanıcı SORMADIĞI bir yakıtın sayılarına
    # kendi yakıtınınki diye bakamaz") aynen korundu, daha güçlü hâlde.
    @pytest.mark.parametrize('yakit', ['ethanol', 'peynir'])
    def test_IKAME_EDILMIYOR_adli_422(self, client, yakit):
        r = _post(client, '/api/get-fuel-properties', {'fuel_type': yakit})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'unknown_fuel'
        assert 'properties' not in govde
        assert 'C12H23' not in json.dumps(govde)

    def test_kendi_kaydi_olan_yakitta_ikame_beyani_YOK(self, client):
        """Sağlıklı yol bit-aynı: gerçek kayıt ikame sayılmaz."""
        r = _post(client, '/api/get-fuel-properties', {'fuel_type': 'rp1'})
        oz = r.get_json()['properties']
        assert oz.get('substituted_record') is None


# ---------------------------------------------------------------------------
# P7B4-05 — /api/flow-analysis boş gövdeden 11 varsayılan (ONARILDI)
# ---------------------------------------------------------------------------
class TestP7B405AkisVarsayilanlari:
    """Ölçüldü (``a4/once.json`` K9): boş gövde HTTP 200 + tam çözüm
    alıyordu ve ``defaults_applied`` YALNIZ ``chamber_pressure``ı
    taşıyordu — kalan sekiz uydurma sayı (3000 K · γ 1,2 · MW 24 ·
    D_t 0,02 m · 101.325 Pa · 45 · 0,40 · 800 K) gövdede hiç geçmiyordu.
    """

    # ÖH D27 / app-api a3 (OH-D26-20) — GÖVDE ÇEVRİLDİ, GEREKÇE:
    # ``{}`` artık 422 alıyor. Beyanın kendisi doğruydu ve ölçülmüştü, ama
    # beyan çözüm değildir (Doktrin 1): motorun HİÇBİR alanı anılmayan bir
    # istekten quasi-1D hüküm üretilemez (kardeş uç
    # ``/api/uncertainty-analysis`` aynı doktrini uyguluyor). İDDİA AYNEN
    # KORUNDU ve motorun ANILDIĞI en küçük gövdeye taşındı: kısmî istekte
    # düşen HER varsayılan hâlâ adıyla beyan edilmek zorunda.
    # Boş gövdenin reddi ``test_d27_app_api_a3.py::
    # TestOHD2620FlowFailClosed`` ile bağlandı.
    #: ÖH D32 / arayuz-panel a2 (OH-D31-14) — GÖVDE İKİNCİ KEZ ÇEVRİLDİ.
    #: D27'nin "motorun ANILDIĞI en küçük gövde"si (tek alan) artık 422
    #: alıyor: kapı alan-alan indi, çünkü D31 form katmanının iki engelini
    #: kaldırdı. Beyan kanalı YOK OLMADI, kapsamı KÜÇÜLDÜ — motoru TAM
    #: tarif eden gövdede düşebilen tek şey üç YÖNTEM seçimidir ve iddia
    #: ("düşen HER varsayılan adıyla beyan edilir") onların üstünde aynen
    #: sınanır. Zorunlu altı alanın beyanla düşemeyeceği ayrıca mandallandı.
    TAM_ASGARI = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
                  'gamma': 1.2, 'molecular_weight': 24.0,
                  'throat_diameter': 0.02, 'ambient_pressure': 101325.0,
                  'expansion_ratio': 4.0}

    def test_bos_govde_HUKUM_ALMAZ(self, client):
        r = _post(client, '/api/flow-analysis', {})
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        assert r.get_json()['error'] == 'incomplete_flow_input'

    def test_kismi_govdede_HER_varsayilan_adiyla_beyan_edilir(self, client):
        from hrma.app import FLOW_REQUIRED_FIELDS
        r = _post(client, '/api/flow-analysis', dict(self.TAM_ASGARI))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        kunye = govde.get('defaults_applied') or []
        beyan = {k['field'] for k in kunye}
        # Düşebilen varsayılanlar: tablodaki sekizden zorunlu olanlar
        # çıkınca kalan ÜÇ yöntem seçimi. Hiçbiri sessiz kalamaz.
        dusebilen = set(FLOW_ANALYSIS_DEFAULTS) - set(FLOW_REQUIRED_FIELDS)
        eksik = dusebilen - beyan
        assert not eksik, (
            'şu varsayılanlar SESSİZ uygulandı: %s' % sorted(eksik))
        # ÖH D32 (OH-D31-14): zorunlu alan künyeyle DÜŞEMEZ.
        assert not (beyan & set(FLOW_REQUIRED_FIELDS)), (
            'zorunlu alan beyanla uyduruldu: %s'
            % sorted(beyan & set(FLOW_REQUIRED_FIELDS)))
        for k in kunye:
            assert k['reason'] == 'not_supplied'
            assert 'assumption, not a result' in k['message']
            assert 'unit' in k and 'value' in k

    def test_zorunlu_alan_eksikse_HICBIR_kunye_uretilmez(self, client):
        """ÖH D32 (OH-D31-14): beyan kanalı kapının yerine geçemez."""
        from hrma.app import FLOW_REQUIRED_FIELDS
        for ad in FLOW_REQUIRED_FIELDS:
            eksik = {k: v for k, v in self.TAM_ASGARI.items() if k != ad}
            r = _post(client, '/api/flow-analysis', eksik)
            assert r.status_code == 422, '%s eksikken çözüldü' % ad
            g = r.get_json()
            assert g['missing_fields'] == [ad], g
            assert g.get('defaults_applied') is None, g

    def test_kunyedeki_deger_COZUCUYE_GIDEN_degerdir(self, client):
        """Künye ile hesap AYNI sabitten beslenir (ÖK-04).

        ÖH D27 a3 (OH-D26-20): gövde ``{}`` yerine motorun ANILDIĞI en
        küçük gövde. ÖH D32 (OH-D31-14): motoru TAM tarif eden gövde.
        ÖK-04 iddiası iki çeviride de değişmedi.
        """
        r = _post(client, '/api/flow-analysis', dict(self.TAM_ASGARI))
        kunye = {k['field']: k['value']
                 for k in r.get_json()['defaults_applied']}
        for ad, (deger, _b, _g) in FLOW_ANALYSIS_DEFAULTS.items():
            if ad in self.TAM_ASGARI:
                continue
            assert kunye[ad] == deger

    def test_deger_gonderilirse_kunye_URETILMEZ(self, client):
        """Sağlıklı yol bit-aynı: beyan yalnız düşüş olduğunda eklenir."""
        tam = {ad: d for ad, (d, _b, _g) in FLOW_ANALYSIS_DEFAULTS.items()}
        tam['chamber_pressure'] = 20.0
        tam['expansion_ratio'] = 4.0
        r = _post(client, '/api/flow-analysis', tam)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert 'defaults_applied' not in r.get_json()


# ---------------------------------------------------------------------------
# P7B4-08 — aynı kavram (fidelity) iki uçta iki sözleşme (ONARILDI)
# ---------------------------------------------------------------------------
KIN_TEMEL = {'of_ratio': 6.0, 'chamber_pressure': 20.0}
# ÖH D32 (OH-D31-14): ``ambient_pressure`` eklendi (zorunlu altıncı alan);
# değer ucun kanonik tablosundan, yayımlanan sayı DEĞİŞMEDİ.
AKIS_TEMEL = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
              'gamma': 1.2, 'molecular_weight': 24.0,
              'ambient_pressure': 101325.0,
              'throat_diameter': 0.02, 'expansion_ratio': 4.0}


class TestP7B408FidelityCaprazSozlesmesi:
    """Ölçüldü (``a4/once.json`` K10): ``fidelity = ''`` gövdesi
    ``/api/flow-analysis``ta 400, ``/api/kinetic-efficiency``te **200** +
    sessiz düşüş alıyordu; üstelik yanıt ``fidelity_requested =
    'engineering'`` yazıyordu — kullanıcının HİÇ yazmadığı seviye.
    """

    @pytest.mark.parametrize('uc,taban', [
        ('/api/flow-analysis', AKIS_TEMEL),
        ('/api/kinetic-efficiency', KIN_TEMEL),
    ])
    @pytest.mark.parametrize('fid', ['peynir', '', '  '])
    def test_gecersiz_seviye_IKI_UCTA_DA_reddedilir(self, client, uc, taban,
                                                    fid):
        r = _post(client, uc, dict(taban, fidelity=fid))
        assert r.status_code == 400, (
            '%s: fidelity=%r sessizce varsayılana düştü (HTTP %s)'
            % (uc, fid, r.status_code))
        assert 'fidelity must be one of' in r.get_json()['error']

    def test_kinetic_KULLANICININ_yazdigini_geri_okur(self, client):
        r = _post(client, '/api/kinetic-efficiency',
                  dict(KIN_TEMEL, fidelity=''))
        assert r.status_code == 400
        assert r.get_json()['fidelity_requested'] == '', (
            'kullanıcının yazmadığı bir seviye "istediğin buydu" diye '
            'geri okunuyor')

    def test_akis_ucu_YAZILANI_geri_okuyor(self, client):
        """Akış ucunda yankı ZATEN vardı: ``fidelity`` alanı kullanıcının
        yazdığıdır (geçersizi kapı 400'le kesiyor), yani bu uçta ikinci
        bir ada gerek yok. Bekçi yankının kaybolmamasını sınar."""
        r = _post(client, '/api/flow-analysis',
                  dict(AKIS_TEMEL, fidelity='fast'))
        assert r.status_code == 200
        assert r.get_json()['fidelity'] == 'fast'

    def test_alan_hic_gonderilmezse_iki_ucta_da_varsayilan(self, client):
        for uc, taban in (('/api/flow-analysis', AKIS_TEMEL),
                          ('/api/kinetic-efficiency', KIN_TEMEL)):
            r = _post(client, uc, dict(taban))
            assert r.status_code == 200, '%s: %s' % (
                uc, r.get_data(as_text=True)[:200])


# ---------------------------------------------------------------------------
# P7B4-10 — /api/cfd/nozzle dayanak alanları (ONARILDI)
# ---------------------------------------------------------------------------
def _cfd_govdesi():
    """Gerçek bir lüle konturu + rezervuar durumu (uç hiçbirini uydurmaz).

    Gövde İKİNCİ KEZ YAZILMAZ: ucun kendi bekçisinin (``test_cfd_endpoint``)
    üreticisi kullanılır — kontur da orada gerçek örnekleyiciden gelir.
    """
    from tests.test_cfd_endpoint import govde
    return govde(resolution='coarse')


class TestP7B410CfdDayanakAlanlari:
    """Ölçüldü (``git grep``, bu worktree): çözücünün ürettiği
    ``time_integrator_basis``, ``mass_flow_in_history``,
    ``mass_flow_out_history``, ``throat_mach_history`` adlarının DÖRDÜ DE
    ``hrma/app.py``de **0 kez** geçiyordu. Uç ``settle_bands`` hükmünü
    ("debi bandı OTURDU/OTURMADI") yayımlıyor ama hükmün dayandığı
    serileri yayımlamıyordu — istemci bandı denetleyemiyordu.
    """

    @pytest.fixture(scope='class')
    def cfd(self, client):
        r = _post(client, '/api/cfd/nozzle', _cfd_govdesi())
        if r.status_code != 200:
            pytest.skip('CFD koşusu bu ortamda kurulamadı: %s'
                        % r.get_data(as_text=True)[:200])
        return r.get_json()['cfd']

    def test_settle_bands_hukmunun_serileri_YAYIMLANIYOR(self, cfd):
        gecmis = cfd.get('convergence_history')
        assert gecmis, 'yakınsama geçmişleri yanıtta yok'
        for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
            blok = gecmis[ad]
            assert blok['n_entries'] > 0, '%s serisi boş' % ad
            assert len(blok['value']) == len(blok['iteration'])
            assert blok['last'] is not None
            assert 'settle_bands' in blok['_basis']

    def test_settle_bands_HALA_yayimlaniyor(self, cfd):
        """Önceki onarımın (P6B1-01) alanı düşmedi."""
        assert cfd['settle_bands']['tol'] is not None
        assert 'mass_flow_in' in cfd['settle_bands']

    def test_zaman_ilerletme_yolu_ADIYLA_yayimlaniyor(self, cfd):
        assert cfd['time_integrator'], 'zaman ilerletme yolu yayımlanmıyor'
        assert 'ssp_rk2' in cfd['time_integrator_basis'], (
            'yolun künyesi taşınmıyor')
        assert cfd['inlet_bc'], 'giriş sınır koşulunun adı yok'
