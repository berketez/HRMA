"""ÖH Dalga-20 · kulvar app-api, aşama 1 — onarım bekçileri.

Her sınıf TEK bir defter kalemini bağlar ve ters-mutasyonla kırmızıya
döndüğü ÖLÇÜLMÜŞTÜR (kanıt: ``docs/scofield/raw/OH/D20/app-api/a1/``,
``once.json`` / ``sonra.json`` / ``mutasyon.json``).

- ``P10B2-05`` (Fable-D18 ŞARTI) — ``_UNIT_RAW_MAX_LEN`` elle yazılmış
  ``6`` idi ve tanınan birimlerin en uzunundan (7) KISAYDI; buradaki
  bekçi tavanın TABLODAN türetildiğini kilitler (ŞART'ın parametreleri
  ``tests/test_d18_app_api_a1.py``'deki kendi sınıfına eklendi).
- ``OH-D19-04`` — ``packaging/hrma.nsi`` kaldırma bölümünün
  ``yabanci_dizin`` dalı, "bu dizin bize ait değil" hükmünü verdikten
  sonra üç alt ağacı KOŞULSUZ ``RMDir /r`` ile siliyordu.
- ``P15B1-02`` (Fable-D18 RET → yeniden atama) — hibrit ``/calculate``
  enjektör plaka kalınlığı beyansız ``3.0`` varsayılanıydı; L/D o
  uydurma sayıdan üretiliyordu.
"""

import json
import os
import re

import pytest

from hrma.app import app

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NSI = os.path.join(DEPO, 'packaging', 'hrma.nsi')


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# P10B2-05 ŞARTI (Fable-D18) — birim adayı tavanı TABLODAN türetilir
# ---------------------------------------------------------------------------
class TestP10B2_05TavanTablodan:
    """Taban ölçümü (``once.json``): ``_UNIT_RAW_MAX_LEN`` = 6, tablo
    maksimumu = 7 ('newtons'/'seconds'). Yani tanınan bir birimin KENDİ
    uzunluğu tavanın üstündeydi ve ``'kilonewton'`` / ``'poundforce'`` /
    ``'minutes'`` beyanları sessizce yutuluyordu (uyarı 0, ``declared_raw``
    ``None``, ``source`` 'assumed (no unit declared)')."""

    def test_tavan_tablo_maksimumunun_ustunde(self):
        from hrma.validation import user_data_validation as u
        tablo_max = max(len(t) for t in u._UNIT_TOKENS)
        assert u._UNIT_RAW_MAX_LEN > tablo_max, (
            f'birim adayı tavanı ({u._UNIT_RAW_MAX_LEN}) tanınan birimlerin '
            f'en uzunundan ({tablo_max}) kısa/eşit — tabloya yeni bir uzun '
            'birim eklendiğinde beyan sessizce yutulur')

    def test_tavan_tabloya_bagli_kalir(self):
        """Tavanı elle bir sayıya döndürmek bu bekçiyi kırar.

        Tablo büyütülünce tavan da büyümeli: bu, iki yerde yazılmış bir
        eşiğin (tavan ⟷ en uzun birim) tek kaynağa bağlanmasıdır.
        """
        import importlib
        from hrma.validation import user_data_validation as u
        eski = dict(u._THRUST_UNIT_FACTORS)
        try:
            u._THRUST_UNIT_FACTORS['averyverylongunitname'] = 1.0
            u._UNIT_TOKENS = (frozenset(u._TIME_UNIT_FACTORS)
                              | frozenset(u._THRUST_UNIT_FACTORS))
            yeni_tavan = max(16, max(len(t) for t in u._UNIT_TOKENS) + 1)
            assert yeni_tavan > 16, 'kurgu kurulmadı'
            # Modül yeniden yüklenince tavan tablodan TÜRETİLMELİ.
            importlib.reload(u)
            assert u._UNIT_RAW_MAX_LEN == max(
                16, max(len(t) for t in u._UNIT_TOKENS) + 1)
        finally:
            u._THRUST_UNIT_FACTORS.clear()
            u._THRUST_UNIT_FACTORS.update(eski)
            importlib.reload(u)

    @pytest.mark.parametrize('ham,rol', [
        ('kilonewton', 'thrust'), ('poundforce', 'thrust'),
        ('minutes', 'time'), ('milliseconds', 'time'),
    ])
    def test_uzun_taninmayan_birim_artik_bildiriliyor(self, ham, rol):
        from hrma.validation.user_data_validation import parse_thrust_csv
        if rol == 'thrust':
            metin = f'Time (s),Thrust ({ham})\n0,0\n1,100\n2,0\n'
        else:
            metin = f'Time ({ham}),Thrust (N)\n0,0\n1,100\n2,0\n'
        out = parse_thrust_csv(metin)
        kunye = out['units'][rol]
        assert kunye['declared_raw'] == ham, kunye
        assert kunye['source'] == f'{"header"} (unrecognized)', kunye
        assert any(ham in w and 'not recognized' in w
                   for w in out['warnings']), out['warnings']
        # Fail-closed'un diğer yüzü: sayı UYDURULMAZ.
        assert kunye['factor_applied'] == 1.0

    def test_uzun_ama_birim_OLMAYAN_parantez_hala_sessiz(self):
        """Yanlış alarm kapısı: boşluk / harf-dışı içerik birim sayılmaz."""
        from hrma.validation.user_data_validation import parse_thrust_csv
        for icerik in ('peak run 3', 'run17', 'test-2'):
            out = parse_thrust_csv(
                f'Time (s),Thrust ({icerik})\n0,0\n1,100\n2,0\n')
            assert out['units']['thrust']['declared_raw'] is None, icerik
            assert not any('not recognized' in w for w in out['warnings']), (
                icerik, out['warnings'])


# ---------------------------------------------------------------------------
# OH-D19-04 — kaldırıcının 'yabancı dizin' dalı koşulsuz siliyordu
# ---------------------------------------------------------------------------
class TestOHD19_04YabanciDizinSilmesi:
    """Taban ölçümü (``once.json``): ``yabanci_dal_rmdir_n`` = 3,
    ``yabanci_dal_dogrulama_var`` = false. Kurulum tarafındaki kapı D19'da
    kapanmıştı (``kurulumda_dogrulama_rmdirden_once`` = true), kaldırma
    tarafı açıktı."""

    @staticmethod
    def _dallar():
        kod = open(NSI, encoding='utf-8', errors='replace').read()
        kaldirma = kod.split('Section "Uninstall"', 1)[1].split(
            'SectionEnd', 1)[0]
        assert 'yabanci_dizin:' in kaldirma, kaldirma[:400]
        return kod, kaldirma, kaldirma.split('yabanci_dizin:', 1)[1]

    def test_kurulum_kapisi_hala_yerinde(self):
        """D19 onarımı bu dalgada bozulmadı (devralınan ayak)."""
        kod, _, _ = self._dallar()
        kurulum = kod.split('Section "HRMA"', 1)[1].split('SectionEnd', 1)[0]
        i = kurulum.find('HrmaDizinKullanilabilirMi')
        silme = [m.start() for m in
                 re.finditer(r'RMDir\s+/r\s+"\$INSTDIR\\', kurulum)]
        assert i >= 0 and silme and i < min(silme), (
            'kurulum bölümünde doğrulama ilk RMDir /r sonrasına kaymış')

    def test_yabanci_dalda_kosulsuz_rmdir_yok(self):
        _, _, yab = self._dallar()
        satirlar = [s.strip() for s in yab.splitlines()]
        for i, s in enumerate(satirlar):
            m = re.match(r'RMDir\s+/r\s+"\$INSTDIR\\(app|libs|python)"', s)
            if not m:
                continue
            onceki = ' '.join(satirlar[max(0, i - 6):i])
            assert re.search(r'IfFileExists|StrCmp', onceki), (
                f'{m.group(1)!r} alt ağacı kanıtsız siliniyor — imza YOKKEN '
                '"bu dizin bize ait değil" denip yine de siliniyor:\n'
                + '\n'.join(satirlar[max(0, i - 6):i + 1]))

    def test_her_alt_agacin_kendi_kaniti_var(self):
        _, _, yab = self._dallar()
        assert 'app\\launcher.py' in yab, (
            "'app' alt ağacı için HRMA izi (app\\launcher.py) aranmıyor")
        assert 'python\\pythonw.exe' in yab, (
            "'python' alt ağacı için HRMA izi (python\\pythonw.exe) "
            'aranmıyor')
        # `libs`in içinde sabit adlı HRMA dosyası yok: düzenin tamamı
        # kanıtlanmadan silinemez.
        i_libs = yab.find('RMDir /r "$INSTDIR\\libs"')
        assert i_libs > 0, 'libs silme satırı kayboldu (adres göçtü)'
        assert re.search(r'StrCmp\s+\$R2\s+"1"', yab[:i_libs]), (
            'libs, kurulum düzeni kanıtlanmadan siliniyor')

    def test_dokunulmayan_alt_agac_kullaniciya_soyleniyor(self):
        """Sessiz atlama yasak: bırakılan ağaç ADIYLA bildirilir."""
        _, _, yab = self._dallar()
        for ad in ('app', 'python', 'libs'):
            assert re.search(rf'DetailPrint\s+"\s*{ad}:.*DOKUNULMADI', yab), (
                f'{ad!r} atlandığında kullanıcıya hiçbir şey söylenmiyor')

    def test_kok_dizin_hala_ozyinelemeli_silinmiyor(self):
        """P10B3-23 ayağı korunur."""
        kod, kaldirma, _ = self._dallar()
        assert not re.search(r'RMDir\s+/r\s+"\$INSTDIR"\s*(;.*)?$',
                             kod, re.M)
        assert re.search(r'RMDir\s+"\$INSTDIR"\s*(;.*)?$', kaldirma, re.M)


# ---------------------------------------------------------------------------
# P15B1-02 — enjektör plaka kalınlığı beyansız varsayılandı
# ---------------------------------------------------------------------------
_HIB = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}


# ÇAPA YENİLENDİ (ÖH D20 birleşim, 3 Eyl 2026): L_D_ratio 3,2337 → 3,9941 — değiştiren D20
# fizik-c B1-12 (34ab8b9): hibrit manşet C_F kayıp kümesi birleşince ṁ→A_t→enjektör delik
# boyutlandırması kaydı; plaka kalınlığı beyanı (bu kalem) değişmedi. Birleşik main'de ölçüldü.
# ÇAPA İKİNCİ KEZ YENİLENDİ (ÖH D23 fix-20, 5 Eyl 2026): 3,9941 → 3,2049 — değiştiren D22
# hibrit a1 (a109e4a/60509f2, OH-D21-03 gerçekleşen L*): η_kin 0,9862201→0,9922190,
# Isp 224,7085→226,0778 s, ṁ_ox 0,388967→0,386611 kg/s; delik çözümü N=50 dalından N=32
# dalına atladı. Gerekçe ve plato ölçümü test_sayi_degismedi künyesinde.
class TestP15B1_02PlakaKalinligi:
    """Taban ölçümü (``once.json``, hibrit ``/calculate``):
    ``injector.plate_thickness`` = 3,0 · ``injector.L_D_ratio`` = 3,2337 ·
    ``plate_thickness_basis`` / ``l_d_ratio_basis`` YOK ·
    ``defaults_applied`` YOK. Kullanıcı hiçbir plaka kalınlığı vermemişken
    yanıt "bu motorun plakası 3,0 mm" diyordu ve hidrolik oranı (L/D) o
    sayıdan üretiyordu; kardeş modül (``engines/injector_design.py``) aynı
    durumda 'the caller supplied neither an orifice length / plate
    thickness nor an L/D' diyor. İki modül artık aynı dili konuşuyor.
    """

    #: V301/E2: L/D bant hükmünün metni "outside optimal range (3-5)" idi;
    #: bandın kaynağı yok, "optimal" kelimesi kaldırıldı ve metin HRMA
    #: buluşsal eşiği olduğunu söylüyor. Bekçi aynı hükmü YENİ metnin L/D'ye
    #: özgü iki parçasıyla tanır (gevşetilmedi: hız bandının metni de
    #: "HRMA heuristic" taşır, L/D önekiyle ayrılır).
    @staticmethod
    def _ld_bant_hukmu(w):
        return ('L/D ratio (' in w and 'band (HRMA heuristic threshold' in w)

    @staticmethod
    def _inj(istemci, **ek):
        r = istemci.post('/calculate', json=dict(_HIB, **ek))
        assert r.status_code == 200, r.status_code
        return (r.get_json() or {}).get('injector') or {}

    def test_verilmeyen_plaka_kalinligi_kunyeli(self, istemci):
        inj = self._inj(istemci)
        temel = inj.get('plate_thickness_basis')
        assert temel, ('plaka kalınlığının nereden geldiği YAZMIYOR — '
                       f'yayımlanan anahtarlar: {sorted(inj)[:40]}')
        assert 'module default' in temel.lower(), temel
        assert inj.get('plate_thickness_earned') is False, inj.get(
            'plate_thickness_earned')

    def test_kazanilmamis_plakadan_hukum_uretilmiyor(self, istemci):
        """L/D KAZANILMAMIŞ bir sayıdan türetilmişse öyle bildirilir."""
        inj = self._inj(istemci)
        temel = inj.get('l_d_ratio_basis')
        assert temel, 'L/D dayanağı yayımlanmıyor'
        assert 'module default' in temel.lower(), temel
        assert inj.get('l_d_ratio_earned') is False
        # Asıl fail-closed ayak: 3-5 bandı HÜKMÜ alıkonur ve alıkonduğu
        # SÖYLENİR. Taban davranışı sessizlikti; sessizlik "L/D'niz uygun"
        # demenin örtülü hâliydi (kimsenin seçmediği bir sayıdan hüküm).
        uyarilar = inj.get('warnings') or []
        assert any('NOT ISSUED' in w and 'L/D' in w for w in uyarilar), (
            f'L/D bandı hükmü kazanılmamış plakadan sessizce veriliyor: '
            f'{uyarilar}')
        assert not any(self._ld_bant_hukmu(w) for w in uyarilar), (
            f'kazanılmamış L/D üzerinden bant hükmü basılmış: {uyarilar}')

    def test_bant_hukmu_ANCAK_kazanilmis_plakadan_verilir(self, istemci):
        """Kapının ateşlendiği çalışma noktası (ÖLÇÜLDÜ).

        ``hole_diameter_min=1,5`` mm ile delik çapı 1,515 mm'ye kilitlenir ve
        L/D = 3,0/1,515 = **1,98** olur, yani 3-5 bandının DIŞINDA. Aynı
        sayıyla:

        * plaka kalınlığı VERİLMEMİŞSE hüküm alıkonur ("NOT ISSUED"),
        * kullanıcı AYNI 3,0 mm'yi kendisi verirse hüküm basılır
          ("L/D ratio (2.0) outside optimal range (3-5)").

        V301/E2: bant artık DEVRE planlayıcısına girer (delik planı
        [1,5; 2,0] mm içinde kurulur: 4 × Ø1,83 mm, L/D 1,64 — yine bandın
        dışında) ve metin "optimal" demez (``_ld_bant_hukmu``).

        Fark sayıda değil, sayının SAHİBİNDEDİR. Varsayılan çalışma
        noktasında (L/D 3,23) bant zaten içeride olduğu için kapı orada
        GÖRÜNMEZ — bu bekçi kapıyı gerçekten ölçen tek kesittir.
        """
        _BANT_DISI = {'hole_diameter_min': 1.5, 'hole_diameter_max': 2.0}
        kazanilmamis = self._inj(istemci, **_BANT_DISI)
        kazanilmis = self._inj(istemci, plate_thickness=3.0, **_BANT_DISI)

        # V301/HİBRİT-DIŞA (kalem 4): kazanılmamış plakada L/D artık
        # YAYIMLANMAZ (null). Kurgunun dayanağı (iki koşu aynı delik planı)
        # delik çapıyla denetlenir; bant dışı L/D kazanılmış koşudan okunur.
        assert kazanilmamis['L_D_ratio'] is None, kazanilmamis['L_D_ratio']
        assert kazanilmamis['hole_diameter'] == pytest.approx(
            kazanilmis['hole_diameter'], rel=1e-9), 'kurgu bozuldu: delik planı ayrıştı'
        assert kazanilmis['L_D_ratio'] < 3.0, kazanilmis['L_D_ratio']

        u_yok = kazanilmamis.get('warnings') or []
        u_var = kazanilmis.get('warnings') or []
        assert not any(self._ld_bant_hukmu(w) for w in u_yok), (
            'kazanılmamış plakadan bant hükmü basıldı: '
            f'{[w for w in u_yok if "L/D" in w]}')
        assert any('NOT ISSUED' in w and 'L/D' in w for w in u_yok), u_yok
        assert any(self._ld_bant_hukmu(w) for w in u_var), (
            'kullanıcı plakayı verdiği hâlde bant hükmü basılmadı — kapı '
            f'hükmü tamamen öldürmüş olur: {u_var}')

    def test_kullanici_verince_kazanilmis_olur(self, istemci):
        inj = self._inj(istemci, plate_thickness=8.0)
        assert inj['plate_thickness'] == pytest.approx(8.0)
        assert inj.get('plate_thickness_earned') is True
        assert inj.get('l_d_ratio_earned') is True
        assert 'caller' in (inj.get('plate_thickness_basis') or '').lower()

    def test_sayi_degismedi(self, istemci):
        """Onarım BEYAN ekler, sayıyı oynatmaz (çapa bit-aynı kalsın).

        ÇAPA YENİLENDİ (ÖH D23 fix-20, 5 Eyl 2026): L/D 3,9940823649 →
        3,2049086463. Plaka kalınlığı 3,0 mm'de KALDI — bu kalemin kendi
        hükmü (kazanılmamışlık beyanı) değişmedi; kayan sayı L/D'dir ve
        kaynağı bu kulvar DEĞİL, D22 hibrit fiziğidir.

        KÖK (ölçüldü, uydurulmadı): ``a109e4a``/``60509f2`` (ÖH D22 hibrit
        a1, defter OH-D21-03) kinetik verimi İSTENEN L* yerine
        GERÇEKLEŞEN L*'tan okuyor; η_kin 0,9862201 → 0,9922190, Isp
        224,7085 → 226,0778 s. Sabit itkide (1000 N) ṁ_ox 0,388967 →
        0,386611 kg/s (−%0,61) ve enjektör gerekli alanı onunla küçülüyor.

        SAYININ NEDEN BU KADAR ZIPLADIĞI (aynı ölçümden): showerhead
        delik sayısı ``_optimize_showerhead_holes`` ile seçiliyor ve
        amaç işlevi L/D ∈ [3, 5] bandında CEZASIZ — yani bant içinde DÜZ.
        ``minimize_scalar`` bu platoda keyfî bir nokta döndürür. Aynı
        ṁ taraması (bu testin çapası, ±%2):
            ×0,995 → N=32, d=0,9337 mm, L/D=3,2130
            ×1,000 → N=32, d=0,9361 mm, L/D=3,2049   (bugünkü çapa)
            ×1,002 → N=50, d=0,7496 mm, L/D=4,0021
        yani %0,2'lik bir ṁ değişimi çözümü N=50 dalından N=32 dalına
        atlatıyor. İki dal da bandın İÇİNDE ve hüküm aynı; bu bir hesap
        hatası değil, PLATO seçiminin kırılganlığıdır. Not olarak
        bırakılıyor — düzeltmesi (plato içinde L/D=4'e en yakın N)
        enjektör fiziğinin kendi kalemidir, bu kulvarın değil.

        ÇAPA ÜÇÜNCÜ KEZ YENİLENDİ (ÖH D25 app-api a3, P16B1-45):
        L/D 3,2049086463 → 3,3830929966; delik çapı 0,9360641226 →
        0,8867624990 mm. Plaka kalınlığı 3,0 mm'de KALDI ve bu kalemin
        kendi hükmü (kazanılmamışlık beyanı) değişmedi — kardeş
        düğümler ``test_verilmeyen_plaka_kalinligi_kunyeli`` ve
        ``test_kazanilmamis_plakadan_hukum_uretilmiyor`` aynen yeşil.

        KÖK (ölçüldü, uydurulmadı): plaka çözücüsü deşarj katsayısını
        ``app.py``deki ÇIPLAK ``data.get('discharge_coefficient', 0.7)``
        yedeğinden alıyordu; aynı yanıtta devre bloğu 0,78 yazıyordu
        (``motor.injector_design.discharge_coefficient``) ve ürünün kendi
        formu da 0,78'i beyan ediyor (``advanced.html`` placeholder +
        "the solver default of 0.78"). Cd artık TEK kaynaktan gelir:
        A = ṁ/(Cd·√(2ρΔP)) olduğu için alan %10,26 küçülür, delik çapı
        %5,27 iner ve L/D = t/d aynı oranda yükselir. Ölçüm:
        docs/scofield/raw/OH/D25/app-api/a3/{once_A,sonra_ABC,
        capa_fark_tam}.json.

        ÇAPA DÖRDÜNCÜ KEZ YENİLENDİ (ÖH D35 onemli-hibrit-fizik a1,
        OH-ON-01, 22 Eylül 2026): delik çapı 0,8867624990 → 2,0678110891 mm,
        L/D 3,3830929966 → 1,4508095134. Plaka kalınlığı yine 3,0 mm'de
        KALDI ve bu kalemin kendi hükmü (kazanılmamışlık beyanı) değişmedi;
        kardeş düğümler aynen yeşil.

        KÖK (ölçüldü, uydurulmadı — docs/scofield/raw/OH/D35/
        onemli-hibrit-fizik/a1/{once,sonra}.json): aynı ``/calculate``
        yanıtında İKİ enjektör çözümü vardı. Bu blok delik planını kendi
        sıkıştırılamaz orifis bağıntısından ve gizli panelin gönderdiği
        ΔP = 0,20·Pc'den türetiyor, devre çözücüsü ise N₂O'nun doyma
        basıncından gelen gerçek ΔP ile (Ornek-H1'de 30,5434 bar) iki-faz
        debisini çözüyordu. Geometri artık TEK kaynaktan — devre
        çözümünden — tüketiliyor, o yüzden delik ÇAPI o çözümün çapıdır ve
        L/D = t/d özdeşliği onunla yeniden kurulur. Sayı bu kulvarın
        fiziğinden değil, iki çözümün uzlaştırılmasından geliyor.
        """
        # V301/HİBRİT-DIŞA (kalem 4, 28 Eki): kazanılmamış plakada
        # plate_thickness / L_D_ratio artık null (fail-closed yayın); çapa
        # sayıları DEĞİŞMEDİ, kullanıcının AYNI 3,0 mm'yi verdiği koşudan
        # okunur (delik planı iki koşuda aynı — test_bant_hukmu_ANCAK_*).
        # V301/T-ÇAPA-D: H-PANEL (74b55500a, Berke onaylı yayımlanan sayı)
        # hibrit c* verimini alan yokken kaynaklı η = 0,89 ile çözüyor →
        # ṁ ↑, delik çapı ↑, L/D 1,4407513659900986 → 1,3596282508507027
        # (oran ≈ √0,89). Bu çapa plaka onarımının SAYIYI OYNATMADIĞINI
        # ölçer; η'dan bağımsız kalsın diye koşu ideal c* (η = %100) ile
        # yapılır. ÖLÇÜLDÜ (28 Eki): η = %100'de L/D bit-aynı 1,4407513659900986
        # (C1'in hibrit kenar vakalarıyla aynı çözüm).
        bos = self._inj(istemci, combustion_efficiency=100)
        assert bos['plate_thickness'] is None and bos['L_D_ratio'] is None, (
            bos['plate_thickness'], bos['L_D_ratio'])
        inj = self._inj(istemci, plate_thickness=3.0, combustion_efficiency=100)
        assert inj['hole_diameter'] == pytest.approx(bos['hole_diameter'], rel=1e-12)
        assert inj['plate_thickness'] == pytest.approx(3.0)
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   L/D 1,4508095133895842 -> 1,4412796945529898
        # v3.0.1 port kulvarı (20 Eki): grain dış çapı = son port (eski
        # 1,5·D_son); kamara küçüldü -> gerçekleşen L* ↓ -> Isp ↓ -> ṁ ↑ ->
        # delik çapı ↑ -> L/D = t/d ↓ (−%0,037). Ölçüldü (birleşik main):
        #   L/D 1,4412796945529898 -> 1,4407513659900986
        assert inj['L_D_ratio'] == pytest.approx(1.4407513659900986,
                                                 rel=1e-9)
        # Çapa TEK sayı değil: L/D = plaka / delik çapı özdeşliği de
        # kilitlenir, yoksa iki sayı sessizce ayrışabilir.
        # ÇAPA YENİLENDİ — kitap p1a B16: delik çapı 2,0678110891284276 ->
        # 2,08148356723394 mm (ṁ arttı; kâhin yukarıda).
        # v3.0.1 port kulvarı (20 Eki): 2,08148356723394 -> 2,0822468545350783
        # mm (+%0,037; L/D ile aynı oran, özdeşlik aşağıda kilitli).
        assert inj['hole_diameter'] == pytest.approx(2.0822468545350783,
                                                     rel=1e-9)
        assert inj['L_D_ratio'] == pytest.approx(
            inj['plate_thickness'] / inj['hole_diameter'], rel=1e-12)

    def test_ai_yuku_isareti_tasiyor(self, istemci):
        """Dışa taşınan belgede sayı KÜNYESİZ yaşayamaz.

        ``prepareAIData`` ``injector_design.plate_thickness_mm``'i yanıttan
        okuyor; kazanılmamışlık işareti aynı blokta yayımlanır.
        """
        r = istemci.post('/calculate', json=dict(_HIB))
        j = r.get_json() or {}
        inj = j.get('injector') or {}
        assert 'plate_thickness_earned' in inj, sorted(inj)[:40]
        govde = json.dumps(j, default=str)
        assert 'plate_thickness_basis' in govde
