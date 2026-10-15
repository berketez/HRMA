"""ÖH Dalga-29 / app-api-uc aşama-1 bekçileri.

Kapatılan kusurlar — hepsi taban ``4c27fa51`` üzerinde ölçüldü
(``docs/scofield/raw/OH/D29/app-api-uc/a1/once*.json``, aynı dizindeki
``olcum*.py`` betikleriyle yeniden üretilebilir):

* **P16B3-26** — ``/api/water-hammer``: ``delta_v_m_s`` ÜÇÜNCÜ bir debi
  tanımıydı ve öteki ikisini SESSİZCE eziyordu. Ölçüm (su hattı
  25,4x1,5 mm, 5 m, 25 bar, ``mdot_kg_s`` 3,74 -> ``v_flow`` 7,395776 m/s):
  ``delta_v_m_s = 1000`` -> HTTP 200 ve tepe 13565,128099 bar (akışın
  kendi hızının 135 KATI bir "kapanma hız değişimi"); ``delta_v_m_s = -5``
  -> HTTP 200 ve tepe 92,700640 bar (``abs()`` işareti yutuyordu).
  ``mdot_kg_s`` ⟷ ``flow_velocity_m_s`` çelişkisi P4B4-10'da kapanmıştı;
  bu üçüncü ayak kapının DIŞINDA kalmıştı.

* **P16B3-27** — ``/api/flow-analysis``: ``expansion_ratio = 1e6``
  reddi SciPy'ın iç metniyle dönüyordu (HTTP 400 ``"f(a) and f(b) must
  have different signs"``); hangi alanın reddedildiği yazmıyordu. Aynı
  uçtaki diğer 11 ret gerekçesi örnek nitelikteydi, bu tek istisnaydı.

* **P16B3-29** — ``/api/uncertainty-analysis``: kapının alt sınırı 2
  iken koşum ``max(50, ...)`` ile kırpıyordu, yani 2..49 aralığı kapıdan
  geçip SESSİZCE 50'ye yükseliyordu (ölçüm: ``n_samples`` 2 / 12 / 30 / 49
  -> HTTP 200 ve yanıtta ``n_samples`` 50). Onarım tabanı YÜKSELTMEZ —
  kullanıcının sayısı aynen koşulur; taban 50'ye çekmek deponun kendi
  sağlıklı gövdelerini (``n_samples: 2`` ve ``12``) reddederdi (ÖK-22).

* **P16B3-30** — ``/parametric-analysis``: ``param_start == param_end``
  kabul ediliyor ve N noktanın hepsi aynı değerde koşuluyordu (ölçüm:
  20/20 -> HTTP 200, beş nokta da 20,0); ``param_start='abc'`` NumPy'ın
  iç metnini döndürüyordu; ``param_start=NaN`` ise HTTP 200 ve
  ``sweep_range: [NaN, 10]`` veriyordu. AZALAN aralık (40 -> 10) kusur
  DEĞİLDİR — yanıt ``sweep_range``i ve nokta başına ``sweep_value``yu
  zaten yayımlıyor; başlığın o yarısı ölçümle çürütüldü ve bilerek
  kabul edilmeye devam ediyor (ÖK-22, sağlıklı envanter daraltılmaz).

* **P16B3-31** — ``/api/analysis/wall-profile``: ``throat_diameter = 0``
  ile ``= -0.03`` BİREBİR aynı sonucu veriyordu (q_MW tepe
  13,673461460390627) ve ikisi de alanın HİÇ gönderilmediği koşumla
  aynıydı; temiz koşu (0,03 m) 13,813239587875527 veriyor. Sayı olmayan
  değer de ``except: pass`` ile yutuluyordu.

* **OH-D17-29** — ``hrma/app.py``de ``/calculate`` yörünge dalı
  ``print(...)`` ile stdout'a yazıyordu (P16B3-14'ün söktüğü desenin
  kopyası; başlatıcı stdout'u destek paketine giren dosyaya yönlendirir).

* **OH-D19-27** (app.py ayağı) — ``R_UNIVERSAL`` ``hrma/app.py`` içinde
  YALNIZ içe aktarma satırında geçiyordu (1 geçiş, 0 kullanım).
"""

import ast
import math

import pytest


# ---------------------------------------------------------------------------
# ÖH D31 fix-34b — ÜRÜN KAYNAĞI DOSYADAN OKUNUR (``inspect.getsource`` DEĞİL)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D31/fix34/b/olcum_getsource_kaymasi.json``):
# taban kaydı-14 süiti PAYLAŞILAN ``main`` çalışma ağacında 64 dakika koştu;
# koşum sürerken D31 kulvar birleşmeleri main'e indi ve ``hrma/app.py`` ile
# ``hrma/engines/liquid_rocket_engine.py`` DİSKTE DEĞİŞTİ. Kod nesneleri içe
# aktarma anındaki (``93b1ab6f``) satır numaralarını taşıyordu;
# ``inspect.getsource`` ise ``linecache`` üzerinden DEĞİŞMİŞ dosyayı okudu.
# ``co_firstlineno`` yeni dosyada başka bir gövdenin ortasına düştü ve
# ``inspect.findsource`` o indeksten GERİYE doğru ilk ``def`` satırını arayıp
# KOMŞU fonksiyonun kaynağını döndürdü (ör. ``_run_uq_analysis`` yerine
# ``_uq_contract_body``, 114 satır kayma; ``flow_analysis`` yerine
# ``_run_kinetic_chain``, 37 satır). Kırmızı ürün kusuru değil, DEĞİŞEN AĞAÇ
# ÜZERİNDE ÖLÇÜM artefaktıydı — ve aynı kayma ters yönde SAHTE YEŞİL de
# üretebilirdi.
#
# Kapı gevşetilmedi, ÖLÇÜM SAĞLAMLAŞTIRILDI: aranan şey zaten ürünün KAYNAK
# METNİdir, o yüzden metin çalışma-anı nesnesinden değil DOSYADAN alınır ve
# hedef gövde AST ile ADIYLA bulunur. Sonuç dosya değişse bile ya doğru
# gövdedir ya da açık bir hatadır; sessiz kayma imkânsızdır.
def _urun_kaynagi(modul, *ad_yolu):
    """``modul``ün dosyasındaki ``ad_yolu`` gövdesinin kaynak metni."""
    import ast as _a
    import pathlib as _p
    yol = _p.Path(getattr(modul, '__file__', '') or '')
    assert yol.is_file(), 'modül dosyası bulunamadı: %r' % (yol,)
    metin = yol.read_text(encoding='utf-8')
    govde = _a.parse(metin).body
    dugum = None
    for ad in ad_yolu:
        dugum = next((d for d in govde
                      if isinstance(d, (_a.FunctionDef, _a.AsyncFunctionDef,
                                        _a.ClassDef)) and d.name == ad), None)
        assert dugum is not None, (
            '%s içinde %r tanımı yok (aranan yol: %s)'
            % (yol.name, ad, '.'.join(ad_yolu)))
        govde = dugum.body
    parca = _a.get_source_segment(metin, dugum)
    assert parca, 'kaynak parçası çıkarılamadı: %s' % '.'.join(ad_yolu)
    return parca


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# --------------------------------------------------------------------------
# P16B3-26 — /api/water-hammer delta_v_m_s
# --------------------------------------------------------------------------
SU_KOCU = {
    'fluid': 'water', 'line_length_m': 5.0, 'line_id_mm': 25.4,
    'wall_thickness_mm': 1.5, 'working_pressure_bar': 25.0,
    'mdot_kg_s': 3.74,
}
#: Ölçülen çözülmüş akış hızı (``mdot_kg_s`` 3,74 -> ``v_flow``).
V_FLOW_OLCULEN = 7.39577595470796


class TestP16B3_26DeltaV:

    def test_akisin_hizindan_buyuk_delta_v_reddedilir(self, istemci):
        """Tabanda HTTP 200 + tepe 13565,128099 bar idi."""
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU, delta_v_m_s=1000.0))
        assert y.status_code == 400, y.status_code
        govde = y.get_json()
        assert 'water_hammer' not in govde, 'hüküm yayımlandı'
        metin = govde['error']
        # Gerekçe hem gönderilen sayıyı hem çözülmüş hızı ADIYLA taşır.
        assert 'delta_v_m_s' in metin
        assert '1000' in metin
        assert 'mdot_kg_s' in metin, 'otoritenin adı gerekçede yok'

    def test_negatif_delta_v_abs_ile_yutulmaz(self, istemci):
        """Tabanda HTTP 200 + tepe 92,700640 bar (işaret yutuluyordu)."""
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU, delta_v_m_s=-5.0))
        assert y.status_code == 400, y.status_code
        assert 'cannot be negative' in y.get_json()['error']

    def test_kismi_kapanma_bit_ayni_kalir(self, istemci):
        """Sağlıklı envanter daraltılmadı (ÖK-22): dv <= v_flow geçer."""
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU, delta_v_m_s=3.0))
        assert y.status_code == 200, y.get_json()
        wh = y.get_json()['water_hammer']
        assert wh['peak_pressure_bar'] == pytest.approx(65.62038429633725,
                                                        rel=1e-9)
        # ``delta_v_source`` yaprağı BİLEREK yayımlanmıyor (ters-yön
        # sözleşmesi: ``_source`` dürüstlük alanıdır ve feed_panel.js
        # arayuz-panel sahası). Kısmi kapanmanın KABUL edildiği ve
        # sayının kullanıcının verdiği dv olduğu ölçülür.
        assert wh['delta_v_m_s'] == pytest.approx(3.0, rel=1e-12)
        assert 'delta_v_source' not in wh, (
            'yaprak açıldı: feed_panel.js kanalı da açılmalı')

    def test_tam_kapanma_kaynagi_adiyla_yayimlanir(self, istemci):
        """Alan gönderilmezse sayı BİT-AYNI, ama kaynağı artık okunabilir."""
        y = istemci.post('/api/water-hammer', json=dict(SU_KOCU))
        assert y.status_code == 200
        wh = y.get_json()['water_hammer']
        assert wh['peak_pressure_bar'] == pytest.approx(125.13975381661594,
                                                        rel=1e-9)
        assert wh['delta_v_m_s'] == pytest.approx(V_FLOW_OLCULEN, rel=1e-9)
        assert 'delta_v_source' not in wh

    def test_sinir_tam_kapanma_kabul_edilir(self, istemci):
        """dv = v_flow TANIMIN kendisidir; sınır dışlanmaz."""
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU, delta_v_m_s=V_FLOW_OLCULEN))
        assert y.status_code == 200, y.get_json()


# --------------------------------------------------------------------------
# P16B3-27 — /api/flow-analysis çözücünün iç metni
# --------------------------------------------------------------------------
# ÖH D32 (OH-D31-14): ``ambient_pressure`` eklendi (zorunlu altıncı alan);
# değer ucun kanonik tablosundan, yayımlanan sayı DEĞİŞMEDİ.
AKIS = {'chamber_pressure': 20.0, 'throat_diameter': 0.03,
        'expansion_ratio': 8.0, 'gamma': 1.2, 'molecular_weight': 22.0,
        'chamber_temperature': 3000.0, 'ambient_pressure': 101325.0}


class TestP16B3_27AlanOrani:

    @pytest.mark.parametrize('eps', [1e6, 1e9])
    def test_cozulemeyen_alan_orani_adiyla_reddedilir(self, istemci, eps):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS, expansion_ratio=eps))
        assert y.status_code == 400, y.status_code
        govde = y.get_json()
        assert govde['error'] == 'unsolvable_area_ratio', govde['error']
        alanlar = govde['invalid_fields']
        assert any(a['field'] == 'expansion_ratio' for a in alanlar), alanlar
        assert any(a['submitted'] == eps for a in alanlar), alanlar
        # Çözücünün ham metni gizlenmez, ama artık TEK BAŞINA gerekçe değil.
        assert 'different signs' in govde['solver_message']

    def test_saglikli_alan_orani_bit_ayni(self, istemci):
        y = istemci.post('/api/flow-analysis', json=dict(AKIS))
        assert y.status_code == 200
        assert y.get_json()['status'] == 'success'


# --------------------------------------------------------------------------
# P16B3-29 — /api/uncertainty-analysis sessiz yukarı kırpma
# --------------------------------------------------------------------------
UQ_D29_GIRDI = {'motor_type': 'hybrid', 'chamber_pressure': 20.0,
            'thrust': 1000.0, 'burn_time': 5.0, 'of_ratio': 6.0,
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}


class TestP16B3_29OrnekSayisi:
    """Kusur İKAMENİN KENDİSİYDİ, küçük örnek sayısı değil.

    Taban ölçümü (``a1/once3.json`` K4): ``n_samples`` 2 / 30 / 49 gönderen
    üç istek de HTTP 200 alıyor ve yanıtta ``n_samples: 50`` görüyordu —
    koşum ``max(50, min(n, 10000))`` ile sessizce yukarı çekiyordu.

    Taban 50'ye YÜKSELTİLMEDİ: küçük örnek sayısı çözülemez bir girdi
    değildir, deponun kendi sağlıklı gövdeleri onu bilerek kullanıyor
    (``test_d28_app_api_a1.py`` ``n_samples: 2``,
    ``test_d27_app_api_a4.py`` ``n_samples: 12``). Onarım: kullanıcının
    sayısı AYNEN koşulur.
    """

    @pytest.mark.parametrize('n', [2, 12, 30, 49])
    def test_istenen_ornek_sayisi_aynen_kosulur(self, istemci, n):
        """Tabanda dördü de yanıtta ``n_samples: 50`` veriyordu."""
        y = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': UQ_D29_GIRDI, 'n_samples': n})
        assert y.status_code == 200, y.get_json()
        assert y.get_json()['n_samples'] == n, 'sayı hâlâ yukarı çekiliyor'

    def test_yukari_cekme_satiri_kaldirildi(self):
        """``_run_uq_analysis``ın KODUNDA ``max(...)`` çağrısı KALMADI.

        Ölçüt yorum metni değil AST'tir: eski kusurun künyesi gövdedeki
        yorumda ``max(50, min(...))`` diye ADIYLA anılıyor ve orada
        kalmalıdır (D26 dersi: künye silinmez). Aranan şey, gerçekten
        çalışan bir ``max`` çağrısıdır.
        """
        import ast as _ast
        import textwrap
        from hrma import app as app_modulu
        # ÖH D31 fix-34b: kaynak metin DOSYADAN, AST ile (bkz.
        # ``_urun_kaynagi`` başlığındaki ölçüm) — ``inspect.getsource``
        # koşum sırasında değişen ağaçta KOMŞU gövdeyi döndürebiliyordu
        # ve bu düğüm "'n' ataması bulunamadı" diye kırmızıya dönmüştü.
        agac = _ast.parse(textwrap.dedent(
            _urun_kaynagi(app_modulu, '_run_uq_analysis')))
        # Yalnız ``n = ...`` ataması incelenir: gövdedeki öteki ``max``
        # (``progress_callback(done / max(total, 1))``) bu kalemle
        # ilgisizdir ve kalmalıdır.
        atamalar = [d for d in _ast.walk(agac)
                    if isinstance(d, _ast.Assign)
                    and any(isinstance(h, _ast.Name) and h.id == 'n'
                            for h in d.targets)]
        assert atamalar, "'n' ataması bulunamadı"
        for atama in atamalar:
            cagrilar = [c.func.id for c in _ast.walk(atama)
                        if isinstance(c, _ast.Call)
                        and isinstance(c.func, _ast.Name)]
            assert 'max' not in cagrilar, (
                'yukarı çekme geri geldi: taban tek kaynaktan da olsa '
                'kullanıcının sayısını YÜKSELTMEK ikamedir')
        assert any('min' in [c.func.id for c in _ast.walk(a)
                             if isinstance(c, _ast.Call)
                             and isinstance(c.func, _ast.Name)]
                   for a in atamalar), 'spec 7.1 tavan kırpması kayboldu'
        assert 'UQ_MAX_SAMPLES' in _urun_kaynagi(
            app_modulu, '_run_uq_analysis')

    def test_saglikli_envanter_daralmadi(self, istemci):
        """ÖK-22: bandın alt ucu (2) ve varsayılan yol değişmedi."""
        from hrma.app import UQ_MIN_SAMPLES
        assert UQ_MIN_SAMPLES == 2
        varsayilan = istemci.post(
            '/api/uncertainty-analysis',
            json={'motor_type': 'hybrid', 'level': 'fast',
                  'inputs': UQ_D29_GIRDI})
        assert varsayilan.status_code == 200
        # Alan gönderilmezse seviye bütçesi geçerlidir — bit-aynı.
        from hrma.analysis.uncertainty import LEVEL_BUDGETS
        assert varsayilan.get_json()['n_samples'] == LEVEL_BUDGETS['fast']

    @pytest.mark.parametrize('n', [1, 0, -5])
    def test_bandin_altindaki_sayi_hala_reddedilir(self, istemci, n):
        """Kurulu kapı (D24 / P16B3-08) sökülmedi."""
        y = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': UQ_D29_GIRDI, 'n_samples': n})
        assert y.status_code == 400
        assert y.get_json()['error'] == 'n_samples_out_of_range'


# --------------------------------------------------------------------------
# P16B3-30 — /parametric-analysis süpürme aralığı
# --------------------------------------------------------------------------
PARAMETRIK = {'motor_type': 'solid', 'param_type': 'chamber_pressure',
              'param_steps': 5, 'throat_diameter': 0.03, 'burn_time': 5.0,
              'propellant_type': 'apcp', 'time_budget_s': 60}


class TestP16B3_30SupurmeAraligi:

    def test_dejenere_aralik_reddedilir(self, istemci):
        """Tabanda HTTP 200 + beş noktanın beşi de 20,0 idi."""
        y = istemci.post('/parametric-analysis',
                         json=dict(PARAMETRIK, param_start=20.0,
                                   param_end=20.0))
        assert y.status_code == 422, y.status_code
        govde = y.get_json()
        assert govde['error'] == 'degenerate_sweep_interval'
        assert not govde.get('results')
        alan = govde['invalid_fields'][0]
        assert alan['field'] == 'param_end'
        assert alan['reason'] == 'equal_to_param_start'

    @pytest.mark.parametrize('ham,gerekce', [
        ('abc', 'not_a_number'),
        (float('nan'), 'not_finite'),
        (float('inf'), 'not_finite'),
    ])
    def test_sayi_olmayan_uc_numpy_metni_dondurmez(self, istemci, ham,
                                                   gerekce):
        """Tabanda 'abc' -> NumPy ufunc metni, NaN -> HTTP 200 idi."""
        y = istemci.post('/parametric-analysis',
                         json=dict(PARAMETRIK, param_start=ham,
                                   param_end=10.0))
        assert y.status_code == 422, y.status_code
        govde = y.get_json()
        assert govde['error'] == 'invalid_sweep_interval'
        assert 'ufunc' not in str(govde), 'NumPy iç metni sızdı'
        alanlar = govde['invalid_fields']
        assert alanlar[0]['field'] == 'param_start'
        assert alanlar[0]['reason'] == gerekce

    @pytest.mark.parametrize('bas,son', [(10.0, 40.0), (40.0, 10.0)])
    def test_artan_ve_azalan_aralik_kabul_edilir(self, istemci, bas, son):
        """AZALAN aralık ÇÜRÜTÜLDÜ: yön yanıtta adıyla duruyor (ÖK-22)."""
        y = istemci.post('/parametric-analysis',
                         json=dict(PARAMETRIK, param_start=bas,
                                   param_end=son))
        assert y.status_code == 200, y.get_json()
        govde = y.get_json()
        assert govde['sweep_range'] == [bas, son]
        degerler = [r['sweep_value'] for r in govde['results']]
        assert degerler[0] == pytest.approx(bas)
        assert degerler[-1] == pytest.approx(son)


# --------------------------------------------------------------------------
# P16B3-31 — /api/analysis/wall-profile gönderilen sayı kaybolmaz
# --------------------------------------------------------------------------
CIDAR = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
         'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
         'mdot_total': 1.0, 'material': 'steel', 'wall_thickness': 0.005}
#: Alanın HİÇ gönderilmediği koşumun ölçülen tepe ısı akısı.
Q_JENERIK = 13.673461460390627
#: Gerçek 30 mm boğazın ölçülen tepe ısı akısı.
Q_TEMIZ = 13.813239587875527


class TestP16B3_31BogazCapi:

    @pytest.mark.parametrize('deger,gerekce', [
        (0, 'must_be_positive'),
        ('0', 'must_be_positive'),
        (-0.03, 'must_be_positive'),
        ('abc', 'not_a_number'),
    ])
    def test_fiziksel_olmayan_bogaz_capi_reddedilir(self, istemci, deger,
                                                    gerekce):
        """Tabanda dördü de HTTP 200 + q_MW tepe 13,673461460390627 idi."""
        y = istemci.post('/api/analysis/wall-profile',
                         json=dict(CIDAR, throat_diameter=deger))
        assert y.status_code == 422, y.status_code
        govde = y.get_json()
        assert govde['error'] == 'invalid_nozzle_input'
        assert 'wall_profile' not in govde, 'profil yayımlandı'
        alan = govde['invalid_fields'][0]
        assert alan['field'] == 'throat_diameter'
        assert alan['reason'] == gerekce
        assert alan['submitted'] == deger

    def test_gercek_bogaz_bit_ayni(self, istemci):
        y = istemci.post('/api/analysis/wall-profile',
                         json=dict(CIDAR, throat_diameter=0.03))
        assert y.status_code == 200
        q = y.get_json()['wall_profile']['q_MW']
        assert max(q) == pytest.approx(Q_TEMIZ, rel=1e-12)

    def test_alan_gonderilmezse_bit_ayni(self, istemci):
        """Sağlıklı envanter daraltılmadı: yokluk hâlâ jenerik profildir."""
        y = istemci.post('/api/analysis/wall-profile', json=dict(CIDAR))
        assert y.status_code == 200
        q = y.get_json()['wall_profile']['q_MW']
        assert max(q) == pytest.approx(Q_JENERIK, rel=1e-12)

    @pytest.mark.parametrize('bos', [None, ''])
    def test_acik_bos_deger_hala_yokluk_sayilir(self, istemci, bos):
        y = istemci.post('/api/analysis/wall-profile',
                         json=dict(CIDAR, throat_diameter=bos))
        assert y.status_code == 200, y.get_json()
        q = y.get_json()['wall_profile']['q_MW']
        assert max(q) == pytest.approx(Q_JENERIK, rel=1e-12)

    def test_iki_farkli_istek_iki_farkli_cevap(self, istemci):
        """Kusurun ÖZÜ: farklı girdiler aynı sayıyı veremez."""
        assert Q_TEMIZ != Q_JENERIK


# --------------------------------------------------------------------------
# OH-D17-29 / OH-D19-27 — kaynak seviyesi bekçileri
# --------------------------------------------------------------------------
def _app_kaynagi():
    import hrma.app as app_modulu
    with open(app_modulu.__file__, encoding='utf-8') as f:
        return f.read()


class TestOHD1729Stdout:

    def test_yorunge_dali_stdout_a_basmaz(self):
        """Tabanda ``app.py``de ``print(f"Trajectory calculation error: …")``
        vardı (K9 ölçümü: 39 ``print`` çağrısı, biri bu satır)."""
        kaynak = _app_kaynagi()
        satirlar = kaynak.splitlines()
        basanlar = [i + 1 for i, ln in enumerate(satirlar)
                    if 'Trajectory calculation error' in ln
                    and 'print(' in ln]
        assert basanlar == [], f'stdout satırı geri geldi: {basanlar}'
        loglayanlar = [i + 1 for i, ln in enumerate(satirlar)
                       if 'Trajectory calculation error' in ln
                       and 'logger' in ln]
        assert loglayanlar, 'kanal tümden kayboldu (hata artık loglanmıyor)'

    def test_calculate_yorunge_hatasi_yanitta_beyanli_kalir(self, istemci):
        """Logger'a taşınırken kullanıcıya dönen beyan DÜŞMEDİ."""
        kaynak = _app_kaynagi()
        assert "'error': f'Trajectory calculation failed:" in kaynak


class TestOHD1927OluIceAktarma:

    def test_R_UNIVERSAL_app_py_de_yok(self):
        """Tabanda ad yalnız içe aktarma satırında geçiyordu (1/0)."""
        kaynak = _app_kaynagi()
        gecen = [i + 1 for i, ln in enumerate(kaynak.splitlines())
                 if 'R_UNIVERSAL' in ln and not ln.lstrip().startswith('#')]
        assert gecen == [], f'ölü içe aktarma geri geldi: {gecen}'

    def test_app_py_hala_iceri_aktarilabilir(self):
        """Söküm bir bağımlılığı kırmadı."""
        import hrma.app as app_modulu
        assert hasattr(app_modulu, 'G_0')
        assert hasattr(app_modulu, 'isa_pressure')

    def test_kaynak_ayristirilabilir(self):
        # iddiasız test yasağı (P13B2-10 / OH-D23-01 bekçisi): ayrıştırma sonucu İDDİA edilir
        agac = ast.parse(_app_kaynagi())
        assert isinstance(agac, ast.Module) and agac.body, 'hrma/app.py ayrıştırılamadı ya da boş'


# --------------------------------------------------------------------------
# OH-D26-20 — kısmen (ÖK-21): tek kaynak + beyan AYAKTA kalır
# --------------------------------------------------------------------------
class TestOHD2620TekKaynakBeyan:
    """Tek kaynak (``FLOW_ANALYSIS_DEFAULTS``) ve ``defaults_applied``
    beyanı geri gitmesin diye mandallanır.

    ÖH D32 / arayuz-panel a2 (OH-D31-14): sınıfın eski künyesi "tam
    fail-closed yarısı ÖK-21 ile kilitli" diyordu; O KİLİT AÇILDI (D31
    ``numById`` anahtarı düşürüyor, ``flow_panel.js``in altı zorunlu alanı
    boş doğuyor) ve kapı alan-alan indi. Beyan kanalı bu yüzden artık
    YALNIZ yöntem seçimlerini (``n_stations``, ``separation_factor``,
    ``wall_temperature``) taşır; zorunlu altı alan düşmez, adıyla istenir.
    """

    def test_varsayilanlar_tek_tablodan_okunur(self):
        from hrma.app import FLOW_ANALYSIS_DEFAULTS
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu.flow_analysis)
        for ad in ('chamber_temperature', 'gamma', 'molecular_weight',
                   'throat_diameter', 'ambient_pressure', 'n_stations',
                   'separation_factor', 'wall_temperature'):
            assert ad in FLOW_ANALYSIS_DEFAULTS, ad
            assert f"FLOW_ANALYSIS_DEFAULTS['{ad}']" in kaynak, (
                f'{ad} varsayılanı uçta İKİNCİ KEZ yazılmış')

    def test_dusen_varsayilan_adiyla_beyan_edilir(self, istemci):
        """ÖH D32 (OH-D31-14) — MANDAL ÇEVRİLDİ, İDDİA KORUNDU.

        Eski gövde ``{'chamber_pressure': 20, 'throat_diameter': 0.03}``
        idi ve BEŞ zorunlu alanın (Tc, gamma, MW, P_amb + Pc) künyeyle
        DÜŞMESİNİ şart koşuyordu — yani kusuru (motorun uydurulmasını)
        beyanla meşrulaştıran bir mandaldı. Zorunlu alanlar artık hiç
        düşmez; gövde motoru TAM tarif eder ve iddia ("düşen her varsayılan
        ADIYLA beyan edilir") düşebilen ÜÇ yöntem seçimi üstünde aynen
        sınanır.
        """
        y = istemci.post('/api/flow-analysis', json=dict(AKIS))
        assert y.status_code == 200
        beyan = y.get_json()['defaults_applied']
        beyanlanan = {a['field'] for a in beyan}
        for ad in ('n_stations', 'separation_factor', 'wall_temperature'):
            assert ad in beyanlanan, f'{ad} sessizce düştü'
        for satir in beyan:
            assert satir['reason'] == 'not_supplied'
            assert 'message' in satir and satir['message']

    def test_zorunlu_alan_DUSMEZ_adiyla_istenir(self, istemci):
        """ÖH D32 (OH-D31-14): beyan kanalı zorunlu alanı YUTAMAZ."""
        from hrma.app import FLOW_REQUIRED_FIELDS
        for ad in FLOW_REQUIRED_FIELDS:
            eksik = {k: v for k, v in AKIS.items() if k != ad}
            y = istemci.post('/api/flow-analysis', json=eksik)
            assert y.status_code == 422, f'{ad} eksikken çözüldü'
            g = y.get_json()
            assert g['missing_fields'] == [ad], g
            assert g.get('defaults_applied') is None, (
                f'{ad} reddedildi ama künye de basıldı — iki kanal '
                'birbirini yutuyor')

    def test_gonderilen_alan_beyanda_yok(self, istemci):
        """Sağlıklı yolun gövdesi bit-aynı: verilen alan künye üretmez."""
        y = istemci.post('/api/flow-analysis', json=dict(AKIS))
        assert y.status_code == 200
        beyan = y.get_json().get('defaults_applied') or []
        beyanlanan = {a['field'] for a in beyan}
        assert 'gamma' not in beyanlanan
        assert 'chamber_temperature' not in beyanlanan


# --------------------------------------------------------------------------
# P16B3-24 — engelli: künyenin DÜRÜST olduğu mandallanır
# --------------------------------------------------------------------------
class TestP16B3_24SinifKunyesi:
    """Kalemin açık yarısı (HTPB/N2O TNT eşdeğeri) Berke'nin fizik kararı
    (OH-D28-APPAPI-01) ve ``hrma/analysis/safety_analysis.py``
    yapisal-sistem sahasıdır. Burada YALNIZ D27'de kazanılan künyenin
    ayakta kaldığı sınanır: tablo dışı bir yakıt için sınıfın KİMDEN
    geldiği yanıttan okunabilmeli.
    """

    EMNIYET_GOVDESI = {'motor_type': 'hybrid', 'chamber_pressure': 20.0,
             'propellant_mass': 50.0, 'chamber_diameter': 0.1,
             'wall_thickness': 0.005}

    def test_tablo_disi_yakit_sinifi_kunyeli(self, istemci):
        y = istemci.post('/analyze_safety',
                         json=dict(self.EMNIYET_GOVDESI, propellant_type='htpb'))
        assert y.status_code == 200, y.get_json()
        metin = str(y.get_json())
        assert 'propellant_class' in metin, 'sınıf künyesi kayboldu'
        assert 'known_propellant_classes' in metin, (
            'tablonun kapsamı yanıttan okunamıyor')
