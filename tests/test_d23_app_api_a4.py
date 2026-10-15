# -*- coding: utf-8 -*-
"""ÖH D23 / app-api aşama-4 bekçileri.

Kapsanan kalemler
-----------------
* **P7B1-13** — ``/api/injector-design`` hata metinleri İngilizce
  (``hrma/app.py:3956``/``:8299`` sözleşmesi: backend EN üretir).
* **P7B1-16** — ``vehicle_mass_dry``ın DÖRT ayrı niyeti tek sonuca çökmez.
* **P7B1-17** — sıfır iticiden sıfır olmayan impuls üretilmez.
* **P7B1-18** — negatif yoğunluk ilgisiz iç mesajla 500 vermez.
* **P7B1-19** — ``gamma <= 1`` uçta da reddedilir (kardeş kapıyla aynı).

Her testin ölçümü ``docs/scofield/raw/OH/D23/app-api/a4/`` altındadır.
"""
import ast
import math
import os
import re

import pytest

from hrma.app import app

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IJ = os.path.join(KOK, 'hrma', 'engines', 'injector_design.py')

#: Türkçe'ye özgü harfler — İngilizce ürün metninde bulunamaz.
TR_HARF = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
#: Türkçe çekim ekleri / sözcükleri (harfsiz de yakalar: "olmali", "gerekli").
TR_SOZCUK = re.compile(
    r'\b(olmal[ıi]|gerekli|zorunlu(dur)?|ge[çc]ersiz|a[şs]mal[ıi]|'
    r'[üu]retilmiyor|i[şs]lemiyor|olamaz|aras[ıi]nda|de[ğg]eri|say[ıi]s[ıi]|'
    r'devresi|desteklenmez|kullan[ıi]n|yaln[ıi]z|beklenen|al[ıi]nan|'
    r'sözlü[ğg]ü|s[oö]zl[uü][ğg][uü])\b', re.I)


def _turkce(metin):
    return bool(TR_HARF.search(metin) or TR_SOZCUK.search(metin))


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


TEMEL = {
    'motor_type': 'hybrid', 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'thrust': 1000, 'burn_time': 10, 'chamber_pressure': 20,
    'of_ratio': 6.0, 'l_star': 1.0,
}


# --------------------------------------------------------------- P7B1-13
class TestP7B113EnjektorHatalariIngilizce:
    """Ölçüm (once_a4.json): 38/38 ``raise`` metni Türkçeydi; uçtan dönen
    sekiz yolun 7'si Türkçe cümle basıyordu. Sözleşme ``hrma/app.py``
    içinde yazılı: *backend EN üretir; TR karşılığı i18n sözlüğünün işidir*.
    """

    def test_kaynakta_turkce_raise_metni_kalmadi(self):
        agac = ast.parse(open(IJ, encoding='utf-8').read())
        kalan = []
        for n in ast.walk(agac):
            if not isinstance(n, ast.Raise):
                continue
            for alt in ast.walk(n):
                if (isinstance(alt, ast.Constant)
                        and isinstance(alt.value, str)
                        and _turkce(alt.value)):
                    kalan.append((n.lineno, alt.value[:70]))
        assert kalan == [], (
            'injector_design.py raise metinleri EN olmalı; Türkçe kalan: '
            f'{kalan}')

    def test_etiket_sozlukleri_ingilizce(self):
        kaynak = open(IJ, encoding='utf-8').read()
        # Etiketler raise metnine {name} olarak giriyor: TR kalırsa mesaj
        # yarı Türkçe çıkar ("... for the oksitleyici circuit").
        assert '_CIRCUIT_LABEL_TR' not in kaynak
        assert '_GAS_POST_LABEL_TR' not in kaynak
        from hrma.engines import injector_design as ij
        for d in (ij._CIRCUIT_LABEL, ij._GAS_POST_LABEL):
            for v in d.values():
                assert not _turkce(v), f'etiket Türkçe kaldı: {v!r}'

    @pytest.mark.parametrize('govde', [
        {'motor_type': 'hybrid', 'injector_type': 'zzz', 'mdot_ox': 1.0,
         'Pc_bar': 20.0},
        {'motor_type': 'hybrid', 'injector_type': 'showerhead',
         'mdot_ox': 0.0, 'Pc_bar': 20.0},
        {'motor_type': 'hybrid', 'injector_type': 'showerhead',
         'mdot_ox': 1.0, 'Pc_bar': 0.0},
        {'motor_type': 'zzz', 'injector_type': 'showerhead', 'mdot_ox': 1.0,
         'Pc_bar': 20.0},
        {'motor_type': 'liquid', 'injector_type': 'like_impinging',
         'mdot_ox': 1.0, 'Pc_bar': 20.0},
        {'motor_type': 'hybrid', 'injector_type': 'showerhead',
         'mdot_ox': 1.0, 'Pc_bar': 20.0, 'discharge_coefficient': 5.0},
        {'motor_type': 'hybrid', 'injector_type': 'gas_gas_coaxial',
         'mdot_ox': 1.0, 'Pc_bar': 20.0},
    ])
    def test_uctan_donen_hata_ingilizce(self, istemci, govde):
        y = istemci.post('/api/injector-design', json=govde)
        assert y.status_code >= 400, 'bu gövdeler reddedilmeliydi'
        g = y.get_json() or {}
        mesaj = str(g.get('error') or g.get('message') or '')
        assert mesaj, 'ret gövdesi hata metni taşımalı'
        assert not _turkce(mesaj), f'Türkçe backend mesajı: {mesaj!r}'


# --------------------------------------------------------------- P7B1-16
class TestP7B116DortNiyetAyrisir:
    """Ölçüm (once_a4.json): ``yok``/``-40``/``0``/``'agir'``/NaN/liste
    ALTISI da HTTP 200 + ``mass_dry = 18,5002595`` + tek künye veriyordu.
    """

    # ÖH D32 fix-35d / OH-D31-10 — ÇAPA KAYMASI (gerekçe kodu kanonu, ana
    # model hükmü 15 Eylül 2026). Paylaşımlı kapı
    # (``app.py::_collect_unphysical_fields``) "JSON sayısı değil" reddini
    # artık merkezin adıyla yayımlıyor (``input_guard.is_json_number`` ->
    # ``not_a_json_number``); ``not_a_number`` EMEKLİ. İDDİA DEĞİŞMEDİ:
    # okunamayan kuru kütle HÂLÂ 400 alıyor ve alan ADIYLA düşüyor —
    # kullanıcının yazdığı değer yerine alt sınır uçurulmuyor.
    @pytest.mark.parametrize('deger,beklenen', [
        (-40, 'must_be_positive'),
        (0, 'must_be_positive'),
        ('agir', 'not_a_json_number'),
        ([1, 2], 'not_a_json_number'),
    ])
    def test_okunamayan_kuru_kutle_adiyla_duser(self, istemci, deger,
                                                beklenen):
        g = dict(TEMEL, vehicle_mass_dry=deger)
        y = istemci.post('/calculate', json=g)
        assert y.status_code == 400, (
            f'{deger!r} kabul edildi (HTTP {y.status_code}) — kullanıcının '
            'yazdığı değer yerine alt sınır uçuruldu')
        alanlar = [f for f in (y.get_json() or {}).get('invalid_fields', [])
                   if f.get('field') == 'vehicle_mass_dry']
        assert alanlar, 'ret alan adını taşımalı'
        assert alanlar[0]['reason'] == beklenen

    def test_sonlu_olmayan_kuru_kutle_adiyla_duser(self, istemci):
        g = dict(TEMEL, vehicle_mass_dry=float('nan'))
        y = istemci.post('/calculate', json=g)
        assert y.status_code == 400
        alanlar = [f for f in (y.get_json() or {}).get('invalid_fields', [])
                   if f.get('field') == 'vehicle_mass_dry']
        assert alanlar and alanlar[0]['reason'] == 'not_finite'

    def test_verilmeyen_kuru_kutle_yolu_bit_ayni(self, istemci):
        """'Vermedim' MEŞRUDUR: alt sınır + künye yolu değişmemeli."""
        y = istemci.post('/calculate', json=dict(TEMEL))
        assert y.status_code == 200
        arac = ((y.get_json() or {}).get('trajectory')
                or {}).get('vehicle_parameters') or {}
        assert arac.get('mass_dry') is not None, (
            'alan gönderilmediğinde alt sınır yolu korunur')

    def test_niyetler_tek_sonuca_cokmez(self, istemci):
        """Kalemin ÖLÇÜSÜ: ayrışan sonuç sayısı 1 değil."""
        imzalar = set()
        for deger in (-40, 0, 'agir', float('nan')):
            y = istemci.post('/calculate',
                             json=dict(TEMEL, vehicle_mass_dry=deger))
            sebep = tuple(sorted(
                f.get('reason')
                for f in (y.get_json() or {}).get('invalid_fields', [])
                if f.get('field') == 'vehicle_mass_dry'))
            imzalar.add((y.status_code, sebep))
        y = istemci.post('/calculate', json=dict(TEMEL))
        imzalar.add((y.status_code, ()))
        assert len(imzalar) >= 4, (
            f'niyetler hâlâ çöküyor, ayrışan imza: {imzalar}')


# --------------------------------------------------------------- P7B1-17
class TestP7B117SifirIticidenImpulsUretilmez:
    """Ölçüm (once_a4.json): ``propellant_mass = 0`` + 25 kNs -> HTTP 200,
    apoje 18 185,8238937 m; 10 kg iticili hâlinden %29,27 YÜKSEK.
    """

    TEMEL_SD = {'dry_mass': 20.0, 'burn_time': 5.0, 'thrust': 5000.0,
                'body_diameter': 0.15}

    def test_sifir_itici_sabit_itki_reddedilir(self, istemci):
        y = istemci.post('/api/six-dof-analysis',
                         json=dict(self.TEMEL_SD, propellant_mass=0.0))
        assert y.status_code == 422, (
            f'sıfır iticiden apoje yayımlandı (HTTP {y.status_code})')
        g = y.get_json() or {}
        alan = [f for f in g.get('invalid_fields', [])
                if f.get('field') == 'propellant_mass']
        assert alan, 'ret alan adını taşımalı'
        assert alan[0]['reason'] == 'zero_propellant_with_nonzero_impulse'
        assert alan[0]['total_impulse_Ns'] == pytest.approx(25000.0)
        # Fail-closed: hüküm yayımlanmaz.
        assert 'summary' not in g and 'apogee_m' not in g

    def test_sifir_itici_itki_egrisi_de_reddedilir(self, istemci):
        egri = {'time': [0.0, 1.0, 2.0], 'thrust': [0.0, 4000.0, 0.0]}
        govde = dict(self.TEMEL_SD, propellant_mass=0.0, thrust_curve=egri)
        govde.pop('thrust')
        govde.pop('burn_time')
        y = istemci.post('/api/six-dof-analysis', json=govde)
        assert y.status_code == 422
        alan = [f for f in (y.get_json() or {}).get('invalid_fields', [])
                if f.get('field') == 'propellant_mass']
        assert alan[0]['reason'] == 'zero_propellant_with_nonzero_impulse'
        # yamuk kuralı: (0+4000)/2*1 + (4000+0)/2*1 = 4000 N.s
        assert alan[0]['total_impulse_Ns'] == pytest.approx(4000.0)

    def test_iticili_kosum_bit_ayni_kalir(self, istemci):
        y = istemci.post('/api/six-dof-analysis',
                         json=dict(self.TEMEL_SD, propellant_mass=10.0))
        assert y.status_code == 200, 'meşru koşum reddedilmemeli'

    def test_itki_alani_yoksa_kapi_sessiz(self, istemci):
        """Var olmayan ihlal uydurulmaz: itki gönderilmemişse kapı susar."""
        govde = {'dry_mass': 20.0, 'body_diameter': 0.15,
                 'propellant_mass': 0.0}
        y = istemci.post('/api/six-dof-analysis', json=govde)
        alan = [f for f in (y.get_json() or {}).get('invalid_fields', [])
                if f.get('reason') == 'zero_propellant_with_nonzero_impulse']
        assert alan == [], 'itki verilmemişken impuls ihlali uyduruldu'

    def test_toplam_impuls_okuyucusu(self):
        from hrma.app import _toplam_impuls_ns as f
        assert f({'thrust': 5000.0, 'burn_time': 5.0}) == 25000.0
        assert f({'thrust_curve': {'time': [0, 2], 'thrust': [100, 100]}}) \
            == pytest.approx(200.0)
        assert f({}) is None
        assert f({'thrust': 'cok', 'burn_time': 5.0}) is None
        assert f({'thrust': True, 'burn_time': 5.0}) is None
        assert f({'thrust': float('nan'), 'burn_time': 5.0}) is None


# --------------------------------------------------------------- P7B1-18
class TestP7B118IlgisizIcMesajYok:
    """Ölçüm (once_a4.json): ``rho_ox = -5`` HTTP **500** +
    *"float() argument must be a string or a real number, not 'complex'"*.
    """

    #: 500 gövdesinde görülen iç ayrıntı sınıfı.
    IC = re.compile(
        r'cannot convert|non-int of type|unsupported operand|'
        r"can't multiply|NoneType|object is not|division by zero|"
        r'invalid literal|float\(\) argument|must be real number', re.I)

    @pytest.mark.parametrize('rho', [-5, 0, -1e-9])
    def test_negatif_yogunluk_500_vermez(self, istemci, rho):
        g = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
             'mdot_ox': 1.0, 'Pc_bar': 20.0, 'rho_ox': rho, 'dP_bar': 5.0}
        y = istemci.post('/api/injector-design', json=g)
        assert y.status_code == 400, (
            f'rho_ox={rho} HTTP {y.status_code} verdi; istemci hatası '
            'sunucu arızası gibi yayımlanamaz')
        mesaj = str((y.get_json() or {}).get('error') or '')
        assert not self.IC.search(mesaj), f'iç ayrıntı sızdı: {mesaj!r}'
        assert 'rho' in mesaj, 'mesaj alan adını taşımalı'

    def test_gecerli_yogunluk_calisir(self, istemci):
        g = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
             'mdot_ox': 1.0, 'Pc_bar': 20.0, 'rho_ox': 800.0, 'dP_bar': 5.0}
        y = istemci.post('/api/injector-design', json=g)
        assert y.status_code == 200

    def test_cozucu_kapisi_dogrudan(self):
        from hrma.engines.injector_design import design_injector
        for rho in (-5.0, 0.0, float('inf')):
            with pytest.raises(ValueError, match='(?i)rho'):
                design_injector({
                    'motor_type': 'hybrid', 'injector_type': 'showerhead',
                    'mdot_ox': 1.0, 'Pc_bar': 20.0, 'rho_ox': rho})


# --------------------------------------------------------------- P7B1-19
class TestP7B119GammaKapisi:
    """Ölçüm (once_a4.json): kardeş kapı ``_parametric_point_rejection``
    ``gamma_must_exceed_one`` derken ``/calculate`` gamma=1,0 ve 0,5 için
    HTTP 200 + ``chamber_volume = 3,7239135e-04`` (İKİSİ DE AYNI) veriyordu.
    """

    @pytest.mark.parametrize('gamma', [1.0, 0.5, 0.0, -2.0])
    def test_gamma_bir_ve_altini_reddeder(self, istemci, gamma):
        y = istemci.post('/calculate', json=dict(TEMEL, gamma=gamma))
        assert y.status_code in (400, 422), (
            f'gamma={gamma} kabul edildi (HTTP {y.status_code})')
        alan = [f for f in (y.get_json() or {}).get('invalid_fields', [])
                if f.get('field') == 'gamma']
        assert alan, 'ret alan adını taşımalı'

    def test_kardes_kapiyla_ayni_hukum(self, istemci):
        """Bir alanın geçerliliği HANGİ UÇTAN geldiğine bağlı olamaz."""
        from hrma.app import _parametric_point_rejection as kardes
        for gamma in (1.0, 0.5):
            assert kardes('gamma', gamma) == 'gamma_must_exceed_one'
            y = istemci.post('/calculate', json=dict(TEMEL, gamma=gamma))
            assert y.status_code >= 400, (
                'süpürmede hesaplanmayan nokta uçta hesaplanıyor')

    @pytest.mark.parametrize('gamma', [1.2, 1.4])
    def test_gecerli_gamma_gecer(self, istemci, gamma):
        y = istemci.post('/calculate', json=dict(TEMEL, gamma=gamma))
        assert y.status_code == 200, f'meşru gamma={gamma} reddedildi'

    def test_gamma_verilmezse_bit_ayni(self, istemci):
        y = istemci.post('/calculate', json=dict(TEMEL))
        assert y.status_code == 200

    def test_hukum_yayimlanmaz(self, istemci):
        """Fail-closed: reddedilen gövdede oda hacmi yayımlanmaz."""
        y = istemci.post('/calculate', json=dict(TEMEL, gamma=1.0))
        govde = y.get_json() or {}
        duz = repr(govde)
        assert 'chamber_volume' not in duz, (
            'reddedilen gövde yine de geometri yayımladı')
        assert math.isfinite(1.0)  # sabit: math kullanımı belgelenir
