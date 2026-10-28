"""ÖH D22 · kulvar app-api · aşama 2/2 — P16 SINIR TURU bekçileri.

Her sınıf bir defter kalemine bağlıdır. Onarım kalemlerinde bekçi
TERS-MUTASYONLA kanıtlanmıştır (onarım geçici geri alınınca KIRMIZI);
çürütülen kalemlerde bekçi kapanışın geri dönmesini engeller.

Ölçümler: ``docs/scofield/raw/OH/D22/app-api/a2/once.json`` (onarım
öncesi) ve ``sonra.json`` (sonrası); ters-mutasyon kanıtı
``mutasyon.json``.
"""
import json
import math

import pytest

from hrma.app import app
from hrma.constants import L_STAR_GENERIC_BAND_M
from hrma.engines.solid_rocket_engine import DESIGN_STATUS_NOT_CONVERGED
from hrma.validation.motor_validation import motor_validator


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}
KATI = {'motor_name': 'D22-A2', 'propellant_type': 'apcp',
        'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
        'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
        'core_diameter': 30.0, 'expansion_ratio': 8.0}
SIVI = {'motor_name': 'D22-A2', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2, 'fuel_type': 'rp1',
        'oxidizer_type': 'lox', 'expansion_ratio': 12.0}
DUVAR = {'chamber_pressure': 30.0, 'chamber_temperature': 3200.0,
         'chamber_diameter': 0.10, 'chamber_length': 0.40, 'burn_time': 8.0,
         'mdot_total': 2.0, 'material': 'steel_4130', 'wall_thickness': 0.006,
         'cooling_type': 'natural', 'throat_diameter': 0.03,
         'exit_diameter': 0.09, 'gamma': 1.22, 'molecular_weight': 26.0,
         'n_stations': 40}


def _yaprak(x, on=''):
    d = {}
    if isinstance(x, dict):
        for k, v in x.items():
            d.update(_yaprak(v, f'{on}.{k}' if on else str(k)))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            d.update(_yaprak(v, f'{on}[{i}]'))
    else:
        d[on] = x
    return d


# ---------------------------------------------------------------- P16B2-05
class TestP16B2_05CozulemeyenHesap422:
    """``burn_rate_n = 1,0``: çözücü yakınsamadı diyorsa HTTP 200 olamaz.

    ÖLÇÜM (once.json): n = 1,00 -> HTTP **200**, ``status='NOT_CONVERGED'``,
    gövde "No performance, CAD or acceptability result is produced from this
    solution" diyor; n = 1,01 -> 400. Yani "kabul edildi" ile "reddedildi"
    arasındaki tek fark bandın üst ucuna dokunmaktı, oysa ikisi de sonuçsuz.
    """

    def test_yakinsamayan_kosum_422(self, client):
        r = client.post('/calculate_solid',
                        json=dict(KATI, burn_rate_n=1.0, burn_rate_a=0.005))
        assert r.status_code == 422, (
            f'yakınsamayan çözüm HTTP {r.status_code} ile yayımlandı')
        j = r.get_json()
        assert j['status'] == DESIGN_STATUS_NOT_CONVERGED

    def test_tani_alanlari_govdede_kaliyor(self, client):
        """Ret bilgi SİLMEZ: tanı gövdesi aynen durur."""
        r = client.post('/calculate_solid',
                        json=dict(KATI, burn_rate_n=1.0, burn_rate_a=0.005))
        j = r.get_json()
        for alan in ('error', 'solver_diagnostics', 'burn_rate_inputs'):
            assert alan in j, f'{alan} rette kayboldu'

    def test_yakinsayan_kosum_200_kaldi(self, client):
        """Sağlıklı yol kıpırdamadı (n = 0,35).

        V301/K-D: aynı gövde (a = 0,005, 5000 N / 3 s) port ⟷ boğaz kısıtlı
        BATES zarfının DIŞINDA: ölçüldü, en küçük itki 5112,12 N, en uzun
        süre 2,967 s. Eski akışta boyutlandırıcı çekirdeği 32,92 mm'ye
        kuruyor ve motorun kendi port kapısından 422 alıyordu (kapı oranı
        0,955). Sağlıklı karşılık zarfın içindeki 2,5 s (ölçülen kapı oranı
        1,746). 3 s'nin adlı zarf reddi tests/test_v301_kd_tasarim_noktasi.py'de.
        """
        r = client.post('/calculate_solid',
                        json=dict(KATI, burn_rate_n=0.35, burn_rate_a=0.005,
                                  burn_time=2.5))
        assert r.status_code == 200
        assert r.get_json().get('status') != DESIGN_STATUS_NOT_CONVERGED

    def test_durum_dizesi_tek_kaynaktan(self):
        """Uç kapısı dizeyi kopyalamaz, motor modülünden okur."""
        import hrma.app as app_mod
        assert (app_mod.SOLID_DESIGN_STATUS_NOT_CONVERGED
                is DESIGN_STATUS_NOT_CONVERGED)


# ---------------------------------------------------------------- P16B2-08
class TestP16B2_08SiviTankBasinciKapisi:
    """``tank_pressure`` fail-closed: NaN/inf çıplak Python hatası veriyordu,
    1e9 bar ise HTTP 200 ile sessizce yutuluyordu (yayımlanan tank basıncı
    2,768 bar — çözücü NPSH'den kendisi boyutlandırıyor).
    """

    @pytest.mark.parametrize('deger', ['NaN', 'Infinity', '-Infinity'])
    def test_sonlu_olmayan_reddedilir(self, client, deger):
        r = client.post('/calculate_liquid', json=dict(SIVI,
                                                       tank_pressure=deger))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_tank_pressure'
        assert j['invalid_fields'][0]['field'] == 'tank_pressure'

    def test_ciplak_python_hatasi_yayimlanmiyor(self, client):
        """Eski gövde ``'<=' not supported between instances of 'str' and
        'float'`` diyordu — iç hata metni, alan adı yok."""
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, tank_pressure='NaN'))
        metin = r.get_data(as_text=True)
        assert "'<=' not supported" not in metin
        assert 'tank_pressure' in metin

    def test_bir_milyar_bar_reddedilir(self, client):
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, tank_pressure=1e9))
        assert r.status_code == 422
        kunye = r.get_json()['invalid_fields'][0]
        assert kunye['max'] == motor_validator.limits['tank_pressure']['max']

    def test_bant_tek_kaynaktan(self, client):
        """Eşik app.py'de İKİNCİ KEZ yazılmaz; doğrulayıcıdan okunur."""
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, tank_pressure=1e9))
        kunye = r.get_json()['invalid_fields'][0]
        bant = motor_validator.limits['tank_pressure']
        assert (kunye['min'], kunye['max'], kunye['unit']) == (
            bant['min'], bant['max'], bant['unit'])

    def test_gecerli_deger_ve_bos_alan_200(self, client):
        """ÖH D27 / OH-D26-12 — ÇEVRİLDİ: "geçerli değer" ÇEVRİME bağlıdır.

        Eski satır ``tank_pressure=45`` için HTTP 200 bekliyordu ve gövdeye
        çevrim yazmadığı için uç turbopompalı varsayılana düşüyordu. Ölçüldü
        (``docs/scofield/raw/OH/D27/sivi/a1/once.json`` OH-D26-12): o 200
        yanıtında 45 bar HİÇBİR yaprağı oynatmıyordu — alan sessizce
        yutuluyordu (yalnız ``inputs_not_used`` beyanı vardı; beyan çözüm
        değildir). Bu testin bant/tip kapısına dair ASIL iddiası korunur:
        bandın İÇİNDEKİ değer bu kapıdan geçer. Değişen, o değerin ardından
        hangi kapının konuştuğudur — basınç beslemeli çevrimde tasarım
        üretilir (200), turbopompalı çevrimde alan okunmadığı için adıyla
        reddedilir (422, ``invalid_tank_pressure`` DEĞİL).
        """
        # Bant içi değer + tank gerçekten enjektörü besliyor -> 200.
        # v3.0.1 T-ÇAPA-B: çözücü basınç beslemede tankı ``feed_pressure``dan
        # okur; o yoksa uç 422 ``pressure_fed_feed_pressure_not_supplied``
        # (L-A SV-03; L-A RAPOR §değişen testler: test_d15_app_api_a2 /
        # test_d27_sivi_a1 için aynı onarım — gövde tankı ``feed_pressure``
        # olarak da verir).
        assert client.post('/calculate_liquid',
                           json=dict(SIVI, engine_cycle='pressure_fed',
                                     tank_pressure=45.0, feed_pressure=45.0)
                           ).status_code == 200
        # Alan hiç gönderilmedi -> çözücünün kendi çözümü, dokunulmaz.
        assert client.post('/calculate_liquid',
                           json=dict(SIVI)).status_code == 200
        # Turbopompalı çevrim: bant kapısı DEĞİL, okunmayan-alan kapısı.
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, tank_pressure=45.0))
        assert r.status_code == 422, r.status_code
        assert r.get_json().get('error') == (
            'tank_pressure_not_read_in_turbopump_cycle'), r.get_json()


# ---------------------------------------------------------------- P16B1-19
class TestP16B1_19LStarUstUcu:
    """``l_star = 1e9`` sessizce kırpılıyor ve ``l_star_note`` BOŞ kalıyordu.

    Küçük tarafta model dürüst bir not yazıyor; büyük tarafta not boştu ve
    kullanıcının sayısı yanıt ağacının üç yerinde yankılanıyordu.
    """

    # ÖH D23 / OH-D22-01 — ÇEVRİLDİ. Eski satır üst ucu SIVI motorun
    # literatür bandına (SP-125 Tablo 4-1 genel aralığı, 3,05 m) demirliyor
    # ve 3,06 m'nin reddedilmesini SÖZLEŞME yapıyordu. Ölçüldü (D23
    # once.json, aynı HİBRİT gövde): o koşu ``l_star_achieved`` = 3,5438 m
    # kuruyor ve modelin kendi notu "Increase L* above that value" diyor —
    # yani ürün önce 3,54 m üstünü öneriyor, sonra 3,06 m'yi kesiyordu; ret
    # gövdesindeki "this model can build a chamber for <= 3,05 m" cümlesi
    # ölçümle yanlıştı. Bekçi artık BANDI değil KURULABİLİRLİĞİ kilitler:
    # kurulabilen değer geçer, kurulamayan (modelin kendi kelepçesinin
    # üstü) hâlâ 422. Testin amacı (sessiz kırpma + boş not yayımlanmasın)
    # değişmedi ve ``test_bos_not_ile_200_yayimlanmiyor`` onu korumaya
    # devam ediyor.
    @pytest.mark.parametrize('deger', [1000.0, 1e9])
    def test_kurulamayan_deger_reddedilir(self, client, deger):
        r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
        assert r.status_code == 422, f'l_star={deger} HTTP {r.status_code}'
        kunye = r.get_json()['invalid_fields'][0]
        assert kunye['field'] == 'l_star'
        assert kunye['reason'] == 'above_model_ceiling'
        assert float(kunye['achieved']) > 0.0

    @pytest.mark.parametrize('kesir', [0.0, 0.5, 0.99])
    def test_kurulabilen_deger_kesilmez(self, client, kesir):
        """Genel bandın üstü ama MODELİN kurabildiği L*: 200 + dolu not.

        v3.0.1 (21 Eki): değerler sabit yazılmaz, bu gövdede modelin KENDİ
        yayımladığı tavandan türetilir. Eski parametreler (3,06 / 4,0 /
        6,0 m) tavanın 6,385 m olduğu geometriye göre seçilmişti; v3.0.1 tane
        zarfı kamara çapını son port çapına indirdi, art-yanma odası tavanı
        (POST_CHAMBER_D_FACTOR_MAX × D_ch) da küçüldü ve tavan 3,862 m oldu
        (ölçüldü). 4 ve 6 m artık gerçekten KURULAMAYAN değerlerdir ve 422
        almaları doğrudur; bekçi kurulabilirliği kilitler, sayıyı değil.
        Aralık: genel bandın 1 cm üstü ile tavan arası.
        """
        r = client.post('/calculate', json=dict(HIBRIT, l_star=1000.0))
        assert r.status_code == 422, r.status_code
        tavan = float(r.get_json()['invalid_fields'][0]['achieved'])
        alt = L_STAR_GENERIC_BAND_M[1] + 0.01
        assert tavan > alt, (
            f'tavan ({tavan:.3f} m) genel bandın üstünde değil; bu bekçinin '
            'öncülü (bandın üstü ama kurulabilir değer) artık yok')
        deger = alt + kesir * (tavan - alt)
        r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
        assert r.status_code == 200, f'l_star={deger} HTTP {r.status_code}'
        assert r.get_json()['motor']['l_star_clamped_high'] is False

    def test_bandin_ust_ucu_kabul(self, client):
        r = client.post('/calculate',
                        json=dict(HIBRIT, l_star=L_STAR_GENERIC_BAND_M[1]))
        assert r.status_code == 200

    def test_kucuk_taraf_dokunulmadi(self, client):
        """Alt uçta model zaten dürüst not yazıyor; 422'ye çevrilmedi."""
        r = client.post('/calculate', json=dict(HIBRIT, l_star=1e-6))
        assert r.status_code == 200
        assert r.get_json()['motor']['l_star_note'].strip() != ''

    def test_bos_not_ile_200_yayimlanmiyor(self, client):
        """Kalemin ÖZÜ: 200 dönen hiçbir gövdede 'l_star yankılandı ama not
        boş' hâli kalmasın."""
        for deger in (1.0, 2.0, L_STAR_GENERIC_BAND_M[1]):
            r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
            assert r.status_code == 200
            m = r.get_json()['motor']
            if abs(float(m['l_star']) - float(m['l_star_achieved'])) > 1e-9:
                assert m['l_star_note'].strip() != '', (
                    f'l_star={deger}: istenen ile ulaşılan farklı ama not boş')


# ---------------------------------------------------------------- P16B1-13
class TestP16B1_13TanimsizMalzemeYankisi:
    """ÇÜRÜTÜLDÜ — kapanış kilidi.

    Başlık: "``/api/advanced-analysis`` tanımsız ``material_type``
    yankılanıyor ama sayılar çelik". ÖLÇÜLDÜ (once.json P16B1-13):
    ``material_type='peynir'`` -> HTTP **422**, yanıtta hiçbir malzeme
    yaprağı yok, hiçbir sayı yayımlanmıyor; ``steel`` ile ``inconel_718``
    yanıtlarının sha256'ları FARKLI (alan gerçekten bağlı).
    """

    GOVDE = {'motor_data': {'chamber_pressure': 20.0,
                            'chamber_temperature': 3000.0,
                            'chamber_diameter': 0.1, 'chamber_length': 0.5,
                            'burn_time': 10.0, 'mdot_total': 1.0},
             'analysis_types': ['heat_transfer'], 'wall_thickness': 0.005}

    def test_tanimsiz_malzeme_sayi_yayimlamiyor(self, client):
        r = client.post('/api/advanced-analysis',
                        json=dict(self.GOVDE, material_type='peynir'))
        assert r.status_code == 422
        yp = _yaprak(r.get_json())
        assert not [v for k, v in yp.items() if 'material' in k.lower()
                    and isinstance(v, (int, float))
                    and not isinstance(v, bool)]

    def test_malzeme_gercekten_bagli(self, client):
        celik = client.post('/api/advanced-analysis',
                            json=dict(self.GOVDE, material_type='steel')
                            ).get_data(as_text=True)
        inconel = client.post('/api/advanced-analysis',
                              json=dict(self.GOVDE,
                                        material_type='inconel_718')
                              ).get_data(as_text=True)
        assert celik != inconel, 'malzeme alanı yanıtı değiştirmiyor'


# ---------------------------------------------------------------- P16B3-05
class TestP16B3_05DuvarProfiliKapisi:
    """ÇÜRÜTÜLDÜ (başlığın ölçülen yarısı) — kapanış kilidi.

    Başlık: "``/api/analysis/wall-profile`` tamamen kapısız: T_c = 1e9 K'de
    999.715.290 K cidar + 6,19e21 MW/m² yayımlanıyor". ÖLÇÜLDÜ (once.json
    P16B3-05): T_c = 1e9 -> **422** ``invalid_wall_profile_input``;
    P_c = 1e9 -> 422; T_c = 'NaN' -> 422. Geçerli gövde 200 ve
    ``T_wall_eq_max`` = 3180,3 K.
    """

    @pytest.mark.parametrize('yama', [
        {'chamber_temperature': 1e9}, {'chamber_pressure': 1e9},
        {'chamber_temperature': 'NaN'}, {'chamber_temperature': -5.0}])
    def test_sinir_disi_girdi_reddedilir(self, client, yama):
        r = client.post('/api/analysis/wall-profile', json=dict(DUVAR, **yama))
        assert r.status_code == 422, f'{yama} -> HTTP {r.status_code}'
        assert 'wall_profile' not in (r.get_json() or {})

    def test_gecerli_govde_makul_cidar(self, client):
        r = client.post('/api/analysis/wall-profile', json=DUVAR)
        assert r.status_code == 200
        T = r.get_json()['wall_profile']['T_wall_eq']
        assert max(T) < 1e5, f'cidar sıcaklığı fiziksel değil: {max(T)}'
        assert all(math.isfinite(t) for t in T)


# ---------------------------------------------------------------- P16B2-10
class TestP16B2_10KatiLuleMalzemesi:
    """ÇÜRÜTÜLDÜ (API ayağı) — kapanış kilidi.

    Başlık: "katıda ``phenolic`` seçmek KRİTİK aşırı-sıcaklık uyarısını
    SESSİZCE yok ediyor — ``status: not_analyzed``, bunu söyleyen satır
    yok". ÖLÇÜLDÜ (once.json P16B2-10): ``phenolic`` -> ``status =
    'not_analyzed'`` YANINDA ``reason = "nozzle material 'phenolic' has no
    materials_db record; no thermal limit is invented"`` — söyleyen satır
    VAR. ``graphite`` ve ``copper`` ise ``warn.solid.
    nozzle_material_over_temp`` uyarısını ``severity='critical'`` ile
    yayımlıyor (T_aw = 3594,9 K; sınırlar 3300 / 1000 K).
    """

    def test_phenolic_sessiz_degil(self, client):
        # V301/T-ÇAPA-D: V301/K-B (36db0dad5) katı malzeme seçeneklerini
        # sunucu kaydından kurdu ve kayıtta olmayan malzemeyi hesaptan ÖNCE
        # adıyla reddediyor (422 unresolved_material; sayfa 'phenolic'
        # seçeneği sunmuyor: page_options). Eski 'not_analyzed' bloğu yerine
        # ret — iddia aynı: sessiz değil, istenen ad ve gerekçe yanıtta.
        r = client.post('/calculate_solid',
                        json=dict(KATI, nozzle_material='phenolic'))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert g['error'] == 'unresolved_material'
        alan = [f for f in g['invalid_fields']
                if f.get('field') == 'nozzle_material']
        assert alan and alan[0]['requested'] == 'phenolic'
        assert alan[0].get('reason') and 'phenolic' in alan[0]['reason']
        assert 'phenolic' not in alan[0].get('page_options', [])

    @pytest.mark.parametrize('malzeme', ['graphite', 'copper'])
    def test_kayitli_malzemede_kritik_uyari_var(self, client, malzeme):
        r = client.post('/calculate_solid',
                        json=dict(KATI, nozzle_material=malzeme))
        blok = r.get_json()['nozzle_material_analysis']
        assert blok['status'] == 'analyzed'
        kodlar = [u['code'] for u in blok['warnings']]
        assert 'warn.solid.nozzle_material_over_temp' in kodlar
        agir = [u['severity'] for u in blok['warnings']
                if u['code'] == 'warn.solid.nozzle_material_over_temp']
        assert 'critical' in agir


# ---------------------------------------------------------------- P16B1-49
class TestP16B1_49GirdiKapisiKapsami:
    """Kök-neden kalemi — ÖLÇÜLDÜ, bu aşamada BİR ayağı bağlandı.

    ÖLÇÜM (once.json P16B1-49): ``/calculate``in okuduğu 83 alanın
    **0**'ı, ``/calculate_solid`` ve ``/calculate_liquid``in 9'ar alanının
    da 0'ı ``input_guard.num`` kapısından geçiyordu — dosya app.py'de
    yalnız YORUMLARDA anılıyordu. Bu bekçi geri dönüşü engeller: ilk
    gerçek çağrı ``/calculate_liquid``in ``tank_pressure`` kapısıdır.
    """

    def test_input_guard_gercekten_cagriliyor(self):
        import ast
        import inspect
        import hrma.app as app_mod
        kaynak = inspect.getsource(app_mod)
        agac = ast.parse(kaynak)
        cagri = [n for n in ast.walk(agac)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ('num', 'integer')
                 and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == 'input_guard']
        assert cagri, ('app.py input_guard.num/integer kapısını hiç '
                       'çağırmıyor (yalnız yorumda anılıyor)')

    def test_limits_alan_adlari_calculate_ile_ortusuyor(self):
        """``motor_validator.limits`` anahtarları hangi uç alanlarına denk
        geliyor — ölçüm dondurulur (kalemin ikinci ayağı)."""
        bant = motor_validator.limits
        assert set(bant) >= {'tank_pressure', 'thrust', 'burn_time',
                             'of_ratio'}
        for ad in ('tank_pressure', 'thrust', 'burn_time'):
            assert {'min', 'max', 'unit'} <= set(bant[ad])
