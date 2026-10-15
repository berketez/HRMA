#!/usr/bin/env python3
"""Sabit çıktı yapraklarını sınıflandırır.

Neden gerekli: bağlama haritası "207 sabit çıktı yaprağı" diyor ve bu sayı
tek başına bir hüküm taşımıyor. Bir kısmı MEŞRU (tarama ızgarası, standart
atmosfer, tanım gereği 1.0), bir kısmı ise henüz bakılmamış. Sayıyı
sınıflandırınca geriye tek anlamlı rakam kalıyor:

    SINIFLANDIRILMAMIŞ = kaç yaprağın neden sabit olduğunu bilmiyoruz

Kapı bunun sıfırlanmasına bağlanabilir. Sonuç: her sayı ya bir amaca
bağlıdır ya da neden bağlı olmadığı YAZILIDIR; belirsiz sayı kalmaz.

Sınıflar
--------
``izgara``    Tarama ekseni / örnekleme noktası. Motora bağlı olmamalı;
              olsaydı grafiğin x ekseni her koşuda kayardı.
``standart``  Fiziksel/standart sabit (ISA atmosferi, yerçekimi). Motorun
              girdisine bağlı olması FİZİK HATASI olurdu.
``tanim``     Tanım gereği sabit: referansa normalize edilen oran (1.0),
              sıra numarası, birim dönüşüm katsayısı.
``beyanli``   Çözücü durumu açıkça bildiriyor: kardeş ``*_basis`` /
              ``*_source`` / ``*_status`` / ``*_definition`` alanı var, ya da
              değer None (üretilmedi diye beyan edilmiş).
``sablon_koru``  Yaprak SABİT DEĞİL: şablonun gönderdiği alanlar onu
              görmüyor, ama payload anahtarı sarsımında OYNUYOR (ölçüm
              kanıtıyla, ``tools/sabit_tarayici.py::tara``). Aklama DEĞİL:
              form o girdiyi taşımıyor demektir, iş listesinde kalır.
``girdi_yankisi``  Yaprak alt-çözümlemenin KENDİ girdisinin yankısıdır
              (``....inputs.<ad>`` düğümü) ve /calculate yükünde onu
              besleyen anahtar YOK. Aklama DEĞİL: formun kapsamadığı bir
              tasarım parametresidir.
``SINIFLANDIRILMAMIS``  Yukarıdakilerden hiçbiri. Bakılacak yer.

ÖH D23 · P15B3-09: son iki sınıf "neden sabit olduğu bilinmiyor" yığınından
ÖLÇÜMLE ayrılmıştır ve AKLAMAZ. ``siniflandir_hepsi`` bunları ayrı bir
``acik_hesap`` kovasında yayımlar; giriş sayfası bir sayfayı bu kova doluyken
"temiz" ilan edemez (bkz. ``tools/wiring_map.py::build_index``).

Kural sırası önemlidir: ``beyanli`` en sona konmaz, çünkü bir ızgara noktası
da beyan taşıyabilir; en açıklayıcı sınıf kazanır.
"""

from __future__ import annotations

import pathlib
import re
import sys

_KOK = pathlib.Path(__file__).resolve().parents[1]
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

#: Kardeş açıklama alanı sonekleri — projenin her yerinde kullanılan sözleşme.
#:
#: ``_available`` KALDIRILDI (27 Ağu 2026, P10B4-08). Gerekçe ölçülmüştür:
#: ``cea_isp_s_available = True`` gibi bir bayrak, kardeşi ``cea_isp_s``in
#: NEREDEN geldiğini söylemez — "var" demek "şu kaynaktan geldi" demek
#: değildir; oysa bu listedeki sonekler tam olarak o soruyu yanıtladığı için
#: aklıyor. Kaldırmanın maliyeti de ölçüldü: üç sayfanın sabit yaprak
#: kümelerinde (solid 162, liquid 305, hybrid 199) ``_available`` soneki
#: TEK BİR yaprağı bile kapatmıyordu (0/0/0), yani kaldırma hiçbir kalemi
#: sınıflandırılmamışa itmiyor, yalnız açık kapıyı kapatıyor.
BEYAN_SONEKLERI = ('_basis', '_source', '_status', '_definition', '_note',
                   '_model', '_reason', '_assumption',
                   # v2.6.26 — projede fiilen kullanilan ama listede olmayan
                   # sonekler (olculdu): hedef/gerceklenen ciftleri, yuk
                   # boyutlandirma bayragi, yontem adi, varsayim bayragi.
                   '_is_target', '_load_sized', '_method', '_assumed',
                   '_tautological', '_labels')

#: Dizi indeksli yol parçası: ``altitude_performance[3]`` gibi.
INDEKS = re.compile(r'\[\d+\]')

#: Tarama ekseni olan yaprak adları. Bunlar SONUÇ değil, sonucun üstünde
#: hesaplandığı noktalardır.
IZGARA_ADLARI = {
    'altitude',          # irtifa taraması
    'altitude_range',
    'time',              # zaman ekseni (sabit adım, solver_diagnostics'te beyanlı)
    'throttle_fraction', # kısma taraması
    'step',              # montaj sırası ordinali
    'index',
    'positions',         # enstrümantasyon yerleşimi (boyutsuz doluluk oranı)
}

#: Standart atmosfer / fiziksel sabit taşıyan yaprak adları. Yalnız bir
#: TARAMA ızgarası altındayken standart sayılır: ``altitude_performance[3]
#: .temperature`` ISA'dır, ama ``chamber.temperature`` sonuçtur.
STANDART_ADLARI = {'temperature', 'pressure', 'density', 'speed_of_sound'}

#: Standart sınıfının geçerli olduğu üst düğümler.
STANDART_KAPSAMLARI = ('altitude_performance', 'atmosphere', 'isa',
                       'thrust_altitude_data', 'altitude_data')

#: Değeri 1.0 olduğunda bu FİZİKSEL bir sonuçtur, tanım gereği normalizasyon
#: DEĞİL — dolayısıyla "referans noktasına normalize edilmiş oran" aklaması
#: bu adlara uygulanmaz (P10B4-08).
#:
#: Ölçüldü (27 Ağu 2026): kural üç sayfada 4 yaprağı kapatıyordu —
#: ``altitude_performance[0].thrust_ratio`` ve ``.isp_ratio`` (deniz
#: seviyesi referansı, gerçekten tanım gereği 1.0) ile
#: ``combustion_analysis.combustion_analysis.optimal_momentum_ratio = 1.0``.
#: Sonuncusu bir hesap sonucudur: enjektör momentum oranının tam 1.0 çıkması
#: "normalize edildi" demek değil, çözücünün verdiği sayıdır. ``expansion_
#: ratio = 1.0`` (lüle yok demektir) de aynı sınıftadır ve bulgunun somut
#: örneğiydi. Liste ADLA çalışır ki dokunulmayan üç normalizasyon aynen
#: aklanmaya devam etsin (bekçi: tests/test_liquid_declarations_v2626.py).
FIZIKSEL_ORANLAR = frozenset({
    'expansion_ratio', 'nozzle_expansion_ratio', 'area_ratio',
    'contraction_ratio', 'of_ratio', 'mixture_ratio',
    'momentum_ratio', 'optimal_momentum_ratio',
})


#: Yaprak adının sonundaki birim jetonu. Beyan kardeşi ararken soyulur:
#: proje sözleşmesinde yaprak `spray_angle_deg` iken beyanı
#: `spray_angle_source` oluyor (birim soneki beyanda taşınmıyor).
BIRIM_SONEKLERI = ('_mm', '_deg', '_k', '_bar', '_mpa', '_pa', '_m', '_s',
                   '_kg', '_kg_m3', '_kg_s', '_m_s', '_percent', '_pct',
                   '_micron', '_um', '_kw', '_w', '_mm2', '_m2', '_l', '_n')


def _son_ad(yol: str) -> str:
    """Yolun son adı (indeks eki atılmış).

    v2.6.26 HATASI (düzeltildi): burada önce ``rstrip(']')`` yapılıyordu,
    yani kapanış parantezi INDEKS regex'inden ÖNCE siliniyordu. Geriye
    ``positions[3`` kalıyor ve ``\\[\\d+\\]`` deseni artık eşleşemiyordu.
    Sonuç: son yol parçası indeksli OLAN HER yaprağın adı yanlış çıkıyor,
    ``altitude_range`` / ``positions`` gibi yazılmış ızgara kuralları hiç
    tetiklenmiyordu (yalnız sıvı sayfasında 21 yaprak).
    """
    parca = yol.split('.')[-1]
    return INDEKS.sub('', parca)


def _birimsiz(ad: str) -> str:
    """Ad sonundaki birim jetonunu soyar (varsa) — EN UZUN eşleşmeyle.

    ÖH D15 / harita H5 — BİLEŞİK BİRİM JETONU GÖLGELENİYORDU. Liste sırayla
    taranıp İLK eşleşmede dönülüyordu; ``_s`` listede ``_m_s``ten ÖNCE
    geldiği için ``line_velocity_band_m_s`` adı ``line_velocity_band_m``e
    soyuluyor ve kardeş beyan araması ``line_velocity_band_m_status`` diye
    var olmayan bir alan arıyordu. ÖLÇÜLDÜ (sıvı sayfası, taban yanıtı):
    ``.feed_system.pressure_drops.{fuel,oxidizer}_line.line_velocity_band_m_s[0]``
    ve ``[1]`` (3,0 ve 8,0 m/s tavsiye bandı) SINIFLANDIRILMAMIŞ görünüyordu,
    oysa AYNI blokta ``line_velocity_band_status = 'within'`` ve
    ``line_diameter_source`` (bandı adıyla anlatan metin) duruyordu.
    En uzun eşleşme aynı adı ``line_velocity_band``e soyar ve kardeş
    bulunur. Soyma TEK kez yapılır: ad zinciri kısaltmak beyan aramasını
    gevşetir, bileşik jetonu doğru seçmek gevşetmez.
    """
    dusuk = ad.lower()
    en_uzun = ''
    for sonek in BIRIM_SONEKLERI:
        if dusuk.endswith(sonek) and len(dusuk) > len(sonek) \
                and len(sonek) > len(en_uzun):
            en_uzun = sonek
    return ad[: -len(en_uzun)] if en_uzun else ad


#: Matematiksel yıldız (``Q*``, ``c*``, ``L*``) — beyan METNİNDE simgeyle,
#: yaprak ADINDA ``_star`` diye yazılır (``q_star_mj_kg`` ⟷ "Q* 8-12 MJ/kg",
#: ``c_star`` ⟷ "c*", ``l_star`` ⟷ "L*"). Jeton eşleşmesi bu iki yazımı
#: aynı sözcük saymadığı için, adını AÇIKÇA anan beyanlar eşleşemiyordu.
#:
#: ÖH D23 · P15B3-09 — ÖLÇÜLDÜ: ``.motor.thermal_protection.chamber_liner.
#: q_star_mj_kg`` yaprağının kardeşi ``source`` alanı "Q* 8-12 MJ/kg
#: literature band, NASA SP-8093 class..." diyor, yani sayının nereden
#: geldiğini BİREBİR söylüyor; buna rağmen yaprak SINIFLANDIRILMAMIŞ
#: görünüyordu çünkü metinde "star" sözcüğü geçmiyordu. Dosyanın kendi
#: yorumu (P10B4-08 bloğu) bu boşluğu zaten yazmıştı ve çözümü zayıf
#: küçük-blok muafiyetine bırakmıştı; bu normalizasyon aynı kalemi GÜÇLÜ
#: dalda kapatır.
#:
#: Desen DAR: yalnız bir HARFİN hemen ardından gelen ``*`` çevrilir
#: (``Q*`` evet, "bkz. *not*" hayır) — gevşetme değil, projenin kendi
#: ASCII yazımının tanınmasıdır.
#:
#: BİRLEŞİK JETON ZORUNLU (ölçülmüş karşı örnek). İlk sürüm ``Q*`` -> 
#: ``Q_star`` çeviriyordu; jetonlayıcı bunu ``{q, star}`` diye ayırıyor ve
#: tek harflik ``q`` eşikte düştüğü için geriye ÇIPLAK ``star`` kalıyordu.
#: Sonuç ÖLÇÜLDÜ (katı sayfası): ``.throat_sizing.reference_case.
#: old_criterion_peak_over_design_percent.star`` ve ``...over_initial_
#: thrust.star`` — YILDIZ GRENİN adı — bloğun ``basis`` metnindeki
#: ``c*`` yüzünden "beyanlı" sayılıp AKLANIYORDU. Metin o yaprağı hiç
#: anmıyor. Bu yüzden iki taraf da TEK jetona indirilir: metinde ``Q*`` ->
#: ``qstar``, adda ``q_star`` -> ``qstar``. ``star`` sözcüğü artık yalnız
#: gerçekten ``star`` yazan metinle eşleşir.
_MATEMATIK_YILDIZ = re.compile(r'([A-Za-z])\*')

#: Adın içindeki ``<harf>_star`` kalıbı (``q_star_mj_kg``, ``c_star``,
#: ``l_star``) — metin tarafındaki ``Q*`` ile AYNI jetona indirilir.
_ADDA_YILDIZ = re.compile(r'(?<![A-Za-z])([A-Za-z])_star(?![A-Za-z])')


def _yildiz_normal(metin: str) -> str:
    """``Q*`` ve ``q_star`` yazımlarını tek jetona (``qstar``) indirger."""
    return _ADDA_YILDIZ.sub(r'\1star', _MATEMATIK_YILDIZ.sub(r'\1star', metin))


def _jetonlar(ad: str) -> set:
    """Yaprak adını sözcüklere ayırır (beyan metniyle eşleştirmek için).

    Eşik 2: kimyasal element simgeleri (``AL``, ``C``, ``N``) iki harflidir ve
    3 harf eşiğiyle hiç jeton üretmiyorlardı — beyan metni alanı anmasına
    rağmen eşleşme kurulamıyordu.
    """
    # Rakam iceren jetonlar SOZCUK degil, birim/indeks artigidir
    # (`grain_thermal_expansion_1k` -> '1k'); beyan metninde gecmezler
    # ve eslesmeyi haksiz yere bozarlar.
    return {j for j in re.split(r'[_\W]+', _yildiz_normal(ad.lower()))
            if len(j) >= 2 and j.isalpha()}


#: ``_kardes_beyan_var`` dallarının adları — hangi yolun akladığı görünür
#: kalsın diye. ``5b`` ZAYIF daldır: beyan metni yaprağın adını hiç anmıyor,
#: yalnız bloğun küçüklüğüne (<= 8 sayısal kardeş) dayanıyor.
DAL_ZAYIF = '5b:kucuk-blok(jetonsuz)'


def _kardes_beyan_var(yol: str, yapraklar: dict, dal: list | None = None
                      ) -> str | None:
    """Yaprağın açıklama alanı var mı? Varsa adını döndürür.

    Aranan biçimler (hepsi projede fiilen kullanılıyor):
      1. Doğrudan kardeş:      ``<yol>_basis``
      2. Birimsiz kardeş:      ``spray_angle_deg`` -> ``spray_angle_source``
      3. Amca sözlük:          ``a.b.c`` -> ``a.mass_method.c`` (AYNI adla)
      4. Paralel blok:         ``a.b.c`` -> ``a.b_source.c``
      5. Blok beyanı:          ``a.b.basis`` — ama YALNIZ metin yaprağın
         adındaki sözcükleri içeriyorsa. Aksi hâlde tek bir ``_basis`` koca
         sözlüğü aklardı; ölçüldü, o biçim ``diffuser_angle`` ve
         ``weber_number`` gibi adı hiç geçmeyen kalemleri de kapatıyordu.
    """
    ad = _son_ad(yol)
    ust = yol.rsplit('.', 1)[0]

    def _isaretle(ad_dal: str):
        if dal is not None:
            dal.append(ad_dal)

    # 1 + 2: doğrudan ve birimsiz kardeş
    for taban in (yol, ust + '.' + _birimsiz(ad)):
        for sonek in BEYAN_SONEKLERI:
            if (taban + sonek) in yapraklar:
                _isaretle(f'1-2:dogrudan/birimsiz({sonek})')
                return taban + sonek

    # 3: amca sözlük — dede altında `<x>_method/_source/_basis/_status`
    #    adlı kardeş sözlükte BİREBİR AYNI anahtar. Ad eşleşmesi zorunlu,
    #    yoksa tek `mass_method` tüm dökümü kutsar.
    dede = ust.rsplit('.', 1)[0] if '.' in ust.lstrip('.') else None
    if dede:
        for sonek in ('_method', '_source', '_basis', '_status'):
            for kardes in list(yapraklar):
                if kardes.startswith(dede + '.') and kardes.endswith(
                        sonek + '.' + ad):
                    _isaretle('3:amca')
                    return kardes

    # 4: paralel blok `a.b_source.c`
    if '.' in ust.lstrip('.'):
        kok, blok = ust.rsplit('.', 1)
        for sonek in ('_source', '_basis', '_status', '_source_labels'):
            aday = f'{kok}.{blok}{sonek}.{ad}'
            if aday in yapraklar:
                _isaretle('4:paralel')
                return aday

    # 5: blok beyanı — JETON EŞLEŞMELİ
    hedef = _jetonlar(_birimsiz(ad))
    for atalar in (ust, ust.rsplit('.', 1)[0] if '.' in ust.lstrip('.') else None):
        if not atalar:
            continue
        for anahtar, deger in yapraklar.items():
            if not anahtar.startswith(atalar + '.'):
                continue
            son = _son_ad(anahtar)
            # ÖH D15 / harita H5 — blok beyanı YALNIZ çıplak adlarla
            # (``basis``/``source``/...) aranıyordu; oysa aynı bloklarda
            # beyan çoğu zaman ÖNEKLİ durur: ``rule_source``, ``band_source``,
            # ``flux_basis``, ``blockage_basis``, ``surface_source``. Bunlar
            # BEYAN_SONEKLERI sözleşmesinin ta kendisidir.
            # Genişletme YALNIZ 5a (jeton eşleşmeli) dalı içindir: metin
            # yaprağın adını anmıyorsa aklama YİNE olmaz. Zayıf 5b dalının
            # kabul ettiği ad kümesi bilerek DAR bırakıldı — küçük-blok
            # muafiyetini genişletmek gerçek bir gevşetme olurdu.
            _cikplak = ('basis', 'status', 'source', 'model', 'method',
                        'assumptions', 'model_note', 'model_limitation')
            _onekli_beyan = son.endswith(BEYAN_SONEKLERI)
            if son not in _cikplak and not _onekli_beyan:
                continue
            metin = str(deger or '').lower()
            if hedef and hedef.issubset(_jetonlar(metin)):
                _isaretle('5a:jeton-eslesti')
                return anahtar
            if not (son in _cikplak or son.endswith('_basis')):
                # Önekli beyan (``rule_source``, ``band_source`` ...) YALNIZ
                # güçlü dalda geçerlidir; zayıf küçük-blok muafiyetinin ad
                # kümesi AYNEN korunur — bu genişletme hiçbir kalemi zayıf
                # yolla kapatmaz. (Ölçüldü: kümeyi daraltmak 5 kalemi
                # beyanli_zayif'ten SINIFLANDIRILMAMIS'a itiyordu; niyet
                # sınıflandırmayı sıkılaştırmak değil, güçlü dalın gözünden
                # kaçan önekli beyanları görünür kılmaktı.)
                continue
            # Jeton eşleşmesi tek başına fazla katı: `q_star_mj_kg` alanının
            # beyanı "Q* 25-30 MJ/kg literatür bandı..." diyor ama metinde
            # "star" sözcüğü geçmiyor. Buna karşılık büyük bir bloğu tek
            # `basis` ile aklamak da yanlış (ölçüldü: `diffuser_angle` ve
            # `weber_number` adı hiç geçmeyen metinlerle kapanıyordu).
            # Orta yol ÖLÇÜLEBİLİR: beyan, KÜÇÜK bir bloğu kapsıyorsa
            # (<= 8 sayısal yaprak) odaklı sayılır ve geçerlidir. Büyük blok
            # yaprak başına beyan ister.
            if anahtar.rsplit('.', 1)[0] == atalar:
                kardes_sayi = sum(
                    1 for k2, v2 in yapraklar.items()
                    if k2.startswith(atalar + '.')
                    and isinstance(v2, (int, float))
                    and not isinstance(v2, bool))
                if kardes_sayi <= 8:
                    # ZAYIF AKLAMA (P10B4-08). Ölçüldü (27 Ağu 2026): bu dal
                    # üç sayfada 44 yaprağı (solid 27, liquid 13, hybrid 4)
                    # beyan metni adlarını HİÇ anmadığı hâlde kapatıyor —
                    # ör. `.acoustic_modes.stability_report.chug.
                    # hard_min_ratio` kardeşi `status = 'OK'` ile "beyanlı"
                    # oluyor; `OK` sayının nereden geldiğini söylemez.
                    # Dal susturulmadı (q_star_mj_kg sınıfı gerçek ihtiyaç)
                    # ama ARTIK SESSİZ DEĞİL: kalem `beyanli_zayif` sınıfına
                    # düşer ve `siniflandir_hepsi` onu `aklananlar` listesinde
                    # ADIYLA yayımlar.
                    _isaretle(DAL_ZAYIF)
                    return anahtar
    return None


#: Örnekleme ekseni taşıyan blok adlarının sonekleri. Bir dizi bu bloklardan
#: birinin altındaysa VE eşit aralıklıysa ızgaradır (bkz. _esit_arali).
IZGARA_BLOK_SONEKLERI = ('_sweep', '_grid', '_axis', '_range')


def _esit_arali(yol: str, yapraklar: dict) -> bool:
    """Bu indeksli yaprağın dizisi ARİTMETİK dizi mi? (ölçülür, varsayılmaz)

    ÖH D15 / harita H5. ``*_sweep`` blokları hem EKSENİ hem SONUCU taşır ve
    ikisi aynı ada benzer: ``fill_sweep.fill_ratio[i]`` eksen,
    ``fill_sweep.slosh_mass_ratio[i]`` o eksende hesaplanan sonuçtur. Adla
    ayırmak uydurma olurdu; ayrım ÖLÇÜLEBİLİR: örnekleme ekseni sabit adımla
    kurulur, sonuç kurulmaz.

    ÖLÇÜLDÜ (hibrit + sıvı taban yanıtı):
      fill_ratio       0,0850 / 0,2585 / 0,4321 ... -> adım 0,173542 SABİT
      slosh_mass_ratio 0,8300 / 0,7789 / 0,6959 ... -> adım -0,0512 / -0,0830
    Yani aynı blokta eksen aritmetik, sonuç değil. Kural sonucu AKLAMAZ:
    ``slosh_mass_ratio`` sınıflandırılmamış kalır ve bu DOĞRUDUR — hiçbir
    form girdisiyle oynamayan bir sonuç ayrı bir sorudur.

    En az 3 nokta ve sıfırdan farklı adım aranır (2 noktalı her dizi
    "aritmetik"tir, aklamaya yetmez).
    """
    m = INDEKS.search(yol)
    if not m:
        return False
    onek = yol[: m.start()]
    seri = []
    i = 0
    while True:
        anahtar = f'{onek}[{i}]'
        if anahtar not in yapraklar:
            break
        v = yapraklar[anahtar]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        seri.append(float(v))
        i += 1
    if len(seri) < 3:
        return False
    adim = seri[1] - seri[0]
    if abs(adim) <= 1e-15:
        return False
    olcek = max(abs(x) for x in seri) or 1.0
    return all(abs((seri[k + 1] - seri[k]) - adim) <= 1e-9 * olcek
               for k in range(len(seri) - 1))


#: ÖLÇÜLEN AÇIK HESAP SINIFLARI (ÖH D23 · P15B3-09). Bunlar "neden sabit
#: olduğu bilinmiyor" yığınından ölçümle ayrılır ama AKLAMAZ: her ikisi de
#: "form bu sayıyı besleyemiyor" demektir ve iş listesinde kalır.
ACIK_HESAP_SINIFLARI = ('sablon_koru', 'girdi_yankisi')

#: Ad karşılaştırmasında "içeriyor" testinin geçerli olduğu EN KISA ad.
#: Kısa anahtarlar (``p``, ``of``) her adın içinde geçer ve kuralı sessizce
#: gevşetirdi.
_AD_ICERME_ESIGI = 4


def _girdi_yankisi_blogu(yol: str, kanit: dict) -> str | None:
    """Yaprak bir alt-çözümlemenin GİRDİ yankısı mı? Blok adını döndürür.

    Koşullar (hepsi ölçülür ya da ürünün kendi sözleşmesinden okunur):

    1. Yaprağın ÜST düğümü birebir ``inputs`` olacak — ürün, çözümlemenin
       aldığı girdiyi bu düğümde geri yayımlar (``pressure_vessel.inputs.
       weld_efficiency``, ``line.inputs.line_length_m``).
    2. Sarsılan payload anahtarları ÖLÇÜLMÜŞ olacak. Ölçüm yoksa hüküm de
       yoktur (fail-closed): "form bu adı taşımıyor" iddiası, taşıyıp
       taşımadığını ölçmeden verilemez.
    3. Payload anahtarları arasında bu adı taşıyan HİÇBİRİ olmayacak — ad
       eşitliği yetmez, KAPSAMA da sayılır (``feed_line_length_m``
       anahtarı ``line_length_m`` yaprağını besliyor olabilir). Böyle bir
       anahtar VARSA yaprak sınıflandırılmamış KALIR: form alanı var ve
       yaprak donmuşsa bu bir aklama konusu değil, bir KUSURDUR.
    """
    ust = yol.rsplit('.', 1)[0]
    if not ust.endswith('.inputs'):
        return None
    anahtarlar = kanit.get('payload_anahtarlari')
    if not anahtarlar:
        return None
    adl = _son_ad(yol).lower()
    adl_birimsiz = _birimsiz(adl)
    for ham in anahtarlar:
        kl = str(ham).lower()
        if kl == adl or _birimsiz(kl) == adl_birimsiz:
            return None
        if (len(kl) >= _AD_ICERME_ESIGI and len(adl) >= _AD_ICERME_ESIGI
                and (kl in adl or adl in kl)):
            return None
    return ust[: -len('.inputs')].strip('.') or '(kök)'


def siniflandir(yol: str, deger, yapraklar: dict,
                kanit: dict | None = None) -> tuple[str, str]:
    """Tek yaprağı sınıflandırır. Döner: (sınıf, gerekçe).

    ``kanit`` (ÖH D23 · P15B3-09) ölçüm kanıtı taşır ve İSTEĞE BAĞLIDIR:

    * ``erime``: ``{yaprak yolu: {'anahtar','deger','taban_deger'}}`` —
      ``tools/sabit_tarayici.py::tara``ın güçlü sarsımında OYNAYAN
      yapraklar ve onları oynatan sarsım. Bu bilgi zaten üretiliyordu,
      yalnız sayısı tutulup adları atılıyordu (kanal var kapı yok).
    * ``payload_anahtarlari``: sarsımın kapsadığı payload anahtarları.

    Verilmezse davranış eskisiyle BİREBİR aynıdır — kanıtsız yeni hüküm
    verilmez.
    """
    ad = _son_ad(yol)
    indeksli = bool(INDEKS.search(yol))

    # 1) Izgara — tarama ekseni / ordinal
    if ad in IZGARA_ADLARI and indeksli:
        return 'izgara', f"tarama ekseni / ornekleme noktasi ({ad})"
    if ad in IZGARA_ADLARI and ad in ('altitude_range',):
        return 'izgara', 'tarama ekseni'

    # 2) Standart — yalnız tarama kapsamı altında
    if ad in STANDART_ADLARI and indeksli and any(
            k in yol for k in STANDART_KAPSAMLARI):
        return 'standart', 'standart atmosfer (ISA / US Std Atm 1976)'

    # 2b) Dizi başlangıç koşulu — `[0]` ve durum ekseni ve değer 0
    #     Faz dizileri FAZ-YERELdir (trajectory_analysis.py:728-734 ötelemeyi
    #     yalnız birleşik diziye uygular), bu yüzden her fazın ilk elemanı
    #     tanım gereği 0'dır; `[1]` canlıdır (ölçüldü).
    if (indeksli and yol.rstrip().endswith('[0]')
            and ad in ('time', 'position_x', 'position_z', 'velocity_x',
                       'velocity_z', 'velocity_magnitude', 'altitude',
                       'acceleration', 'range',
                       # ÖH D15 / harita H5 — eksenin BAŞLANGIÇ NOKTASI.
                       # Lüle istasyon ekseni x = 0'dan başlar (ölçüldü:
                       # .nozzle_flow_quasi1d.x_m[0] = 0,0 katıda ve
                       # .motor.nozzle_flow_quasi1d.stations.x_m[0] = 0,0
                       # hibritte); [1] ve sonrası canlıdır. Faz dizisi
                       # t=0 ile aynı sınıf.
                       'x_m', 'x', 'z_m', 'station_x_m', 'arc_length_m')
            and isinstance(deger, (int, float)) and not isinstance(deger, bool)
            and abs(float(deger)) < 1e-12):
        return 'tanim', 'integrasyon baslangic kosulu (faz-yerel t=0)'

    # 2b-2) MOD NUMARALANDIRMA EKSENİ (ÖH D15 / harita H5).
    #    ``modes[k].indices.{longitudinal_q, radial_n, tangential_m}`` ve
    #    ``modes[k].mode`` HANGİ modun raporlandığını söyleyen (m, n, q)
    #    üçlüsüdür — sonuç değil, sonucun üstünde hesaplandığı sıralamadır.
    #    ÖLÇÜLDÜ (üç sayfanın taban yanıtı): aynı ``modes[k]`` düğümündeki
    #    ``frequency_hz`` yapraklarının HEPSİ canlıdır (hibrit 48/48,
    #    katı 16/16, sıvı 10/10 — sabit sayısı sıfır), indeks üçlüsü ise
    #    sabittir. Motorun girdisiyle DEĞİŞSEYDİ mod listesinin kimliği her
    #    koşuda kayardı ve "1L" etiketi başka bir modu gösterirdi.
    if indeksli and ('.modes[' in yol or '.modes.' in yol):
        ust_ad = _son_ad(yol.rsplit('.', 1)[0]) if '.' in yol.lstrip('.') else ''
        if ust_ad == 'indices' or ad in ('mode', 'mode_number', 'order'):
            return 'izgara', 'mod numaralandirma ekseni (m, n, q) — frekans ayri yaprakta ve canli'

    # 2b-3) EŞİT ARALIKLI ÖRNEKLEME EKSENİ (ÖH D15 / harita H5).
    #    ``*_sweep`` / ``*_grid`` / ``*_axis`` / ``*_range`` bloğunun altındaki
    #    indeksli dizi ARİTMETİKSE tarama eksenidir. Ölçülür (_esit_arali),
    #    adına bakılarak varsayılmaz: aynı blokta duran SONUÇ dizileri
    #    aritmetik olmadıkları için aklanmaz.
    if indeksli and isinstance(deger, (int, float)) \
            and not isinstance(deger, bool):
        _blok = yol.rsplit('.', 1)[0]
        _blok_ad = _son_ad(_blok)
        if _blok_ad.endswith(IZGARA_BLOK_SONEKLERI) and _esit_arali(yol, yapraklar):
            return 'izgara', f'esit arali ornekleme ekseni ({_blok_ad} blogu)'

    # 2c) Sayısal çözünürlük / ızgara parametresi — motora bağlı olmamalı
    if (re.search(r'(_stations|_nodes|_samples|_points|_steps|_resolution)$', ad)
            or ad.startswith('n_') or ad == 'time_step'):
        return 'izgara', 'sayisal ayriklastirma cozunurlugu'

    # 2d) Uyarı yükü — uyarının parametresi hesap çıktısı değil, beyanın
    #     kendisidir (`warnings[*].params.*`).
    if '.params.' in yol and ('warnings[' in yol or 'warning' in yol):
        return 'beyanli', 'uyari yuku (beyanin kendisi)'

    # 2e) materials_db okuması — blokta `material_key` kardeşi varsa malzeme
    #     özellikleri çözücü çıktısı değil, veritabanı kaydıdır.
    ust_dugum = yol.rsplit('.', 1)[0]
    if (re.match(r'^(density|yield_strength|elastic_modulus|poisson|'
                 r'thermal_conductivity|specific_heat|ultimate_strength)',
                 _birimsiz(ad))
            and (ust_dugum + '.material_key') in yapraklar):
        return 'standart', 'materials_db kaydi (material_key kardesi var)'

    # 3) Tanım gereği
    if isinstance(deger, (int, float)) and not isinstance(deger, bool):
        if (abs(float(deger) - 1.0) < 1e-12
                and ('ratio' in ad or ad.endswith('_ratio'))
                and _birimsiz(ad).lower() not in FIZIKSEL_ORANLAR):
            return 'tanim', 'referans noktasina normalize edilmis oran (=1.0)'
    if ad == 'step' or ad == 'index':
        return 'tanim', 'sira numarasi / ordinal'

    # 4) Beyanlı — cozucu durumu aciklamis
    dal: list = []
    beyan = _kardes_beyan_var(yol, yapraklar, dal)
    if beyan is not None:
        alan = beyan.rsplit('.', 1)[-1]
        if dal and dal[-1] == DAL_ZAYIF:
            return ('beyanli_zayif',
                    f'ZAYIF aklama ({DAL_ZAYIF}): kardes aciklama alani '
                    f'{alan}, ama metin yapragin adini anmiyor — kucuk blok '
                    f'muafiyeti')
        return 'beyanli', f'kardes aciklama alani: {alan}'
    if deger is None:
        return 'beyanli', 'deger uretilmedi (None) — modellenmedigi bildirilmis'

    # 5) ÖLÇÜLEN AÇIK HESAPLAR (ÖH D23 · P15B3-09) — AKLAMA DEĞİL.
    #    Bu iki dal "bilinmiyor"u "biliyorum ama iyi haber değil"e çevirir;
    #    ikisi de yaprağı ``acik_hesap`` kovasında bırakır.
    if kanit:
        _er = (kanit.get('erime') or {}).get(yol)
        if _er:
            return ('sablon_koru',
                    'SABIT DEGIL: sablon sarsimi goremedi, payload anahtari '
                    "'%s' %r -> %r yapilinca OYNUYOR (guclu sarsim olcumu, "
                    'tools/sabit_tarayici.py::tara) — form bu girdiyi '
                    'tasimiyor'
                    % (_er.get('anahtar'), _er.get('taban_deger'),
                       _er.get('deger')))
        _blok = _girdi_yankisi_blogu(yol, kanit)
        if _blok is not None:
            return ('girdi_yankisi',
                    "alt-cozumlemenin GIRDI yankisi ('%s.inputs' dugumu): "
                    'sarsilan %d payload anahtarindan hicbiri bu adi '
                    'tasimiyor, deger cozumlemenin varsayilani — form onu '
                    'beslemiyor'
                    % (_blok, len(kanit.get('payload_anahtarlari') or ())))

    return 'SINIFLANDIRILMAMIS', 'neden sabit oldugu bilinmiyor'


def _denetlenen_ayna_kokleri() -> tuple:
    """Ayna köklerinin TEK KAYNAĞI: ``tests/support/shake.py``.

    P10B4-09: bu liste burada elle yazılıyordu (7 kök) ve bit-aynılığı
    denetleyen liste ``shake.ECHO_CANONICAL_PREFIXES`` 5 kökten ibaretti.
    Yani AKLAYAN liste DENETLEYEN listeden genişti ve ikisini senkron tutan
    hiçbir bekçi yoktu; aklayan listeye kök eklemek denetimi otomatik
    genişletmiyordu. Artık ortak gövde tek yerde tanımlıdır ve buradan içe
    aktarılır; ayrışma ``tests/test_z5s_kampanya_araclari.py`` bekçisinde
    kırmızıya döner.

    İçe aktarma FAIL-CLOSED'dır: shake okunamazsa sessizce elle yazılmış bir
    yedeğe düşmek, kapattığımız ayrışmayı geri getirirdi.
    """
    from tests.support import shake
    return tuple((onek + '.', kanonik + '.')
                 for onek, kanonik in shake.ECHO_CANONICAL_PREFIXES)


#: Bit-aynılığı ``shake`` tarafında da denetlenen kökler (tek kaynak).
AYNA_KOKLERI_DENETLENEN = _denetlenen_ayna_kokleri()

#: Yalnız BURADA tanınan, ``shake``in sayfa-bağımsız sözleşmesine
#: sığmayan kökler — her biri GEREKÇESİYLE. Sessiz fazlalık yok.
#:
#: Ölçüm (27 Ağu 2026, üç sayfanın taban yanıtı): B4 raporu
#: ``.motor_geometry.nozzle_angles``ı "yanıtta karşılığı olmayan ölü kayıt"
#: diye işaretlemişti; bu YALNIZ HİBRİT için doğru. Katıda 10, sıvıda 16
#: yaprağı var ve ikisinde de ``.nozzle_angles`` ile 10/10 ve 16/16
#: BİT-AYNI. Ters yönde: ``.motor.nozzle_angles`` yalnız hibritte var
#: (4 yaprak, 4/4 bit-aynı); katı ve sıvıda hiç yok, yani o sayfalarda
#: kanonik olan ``.nozzle_angles``ın kendisidir. ``shake`` sözleşmesi
#: "kanonik yaprak yoksa İHLAL" dediği ve sayfa ayrımı yapmadığı için bu
#: kökü oraya taşımak katı+sıvıda 26 SAHTE ihlal üretirdi.
AYNA_KOKLERI_DENETLENMEYEN = {
    ('.nozzle_angles.', '.motor.nozzle_angles.'):
        'Kanonik yalnız HİBRİTTE var (4/4 bit-aynı); katı ve sıvıda '
        '.motor.nozzle_angles hiç yayımlanmıyor, o sayfalarda kanonik '
        'olan .nozzle_angles kendisidir — sayfa-bağımsız shake '
        'sözleşmesine sığmıyor.',
    ('.motor_geometry.nozzle_angles.', '.nozzle_angles.'):
        'Kanonik yalnız KATI (10/10) ve SIVIDA (16/16) var; hibritte '
        '.motor_geometry.nozzle_angles hiç yayımlanmıyor. Aynı sayfa '
        'asimetrisi.',
}

#: Aynı sözlüğün yanıtta ikinci/üçüncü kez yayımlandığı kökler.
#: app.py motor sonucunu hem `.motor` altına, hem OpenRocket dalına, hem de
#: yörünge dalına koyuyor — birebir AYNI nesne. Bu yapraklar ayrı bir bulgu
#: değildir; kanonik kopyanın sınıfını miras alırlar. Aksi hâlde tek bir
#: sabit üç kez sayılıyor ve "sınıflandırılmamış" rakamı şişiyor.
AYNA_KOKLERI = AYNA_KOKLERI_DENETLENEN + tuple(AYNA_KOKLERI_DENETLENMEYEN)


def siniflandir_hepsi(sabit_yollar, yapraklar: dict,
                      kanit: dict | None = None) -> dict:
    """Sabit yaprak listesini sınıflandırır.

    Döner: ``{'sayim': {sınıf: adet}, 'kalemler': [(yol, sınıf, gerekçe)...],
    'aklananlar': [...], 'acik_hesap': [...]}``

    ``acik_hesap`` (ÖH D23 · P15B3-09): ölçümle AÇIKLANAN ama AKLANMAYAN
    kalemler — ``sablon_koru`` ve ``girdi_yankisi``. Ayrı yayımlanır ki
    "sınıflandırılmamış" sayısının düşmesi bir temizlik sanılmasın: bu iki
    sınıf da "form bu sayıyı besleyemiyor" demektir.
    """
    yollar = list(sabit_yollar)
    ilk: dict[str, tuple[str, str]] = {}
    for yol in yollar:
        ilk[yol] = siniflandir(yol, yapraklar.get(yol), yapraklar, kanit)

    from tests.support import shake

    kalemler = []
    aklananlar = []
    acik_hesap: list = []
    sayim: dict[str, int] = {}
    for yol in yollar:
        sinif, gerekce = ilk[yol]
        # Ayna kökündeki yaprak AYRI BİR İŞ DEĞİLDİR: kanonik kopya
        # düzeltilince o da düzelir. Kanonik henüz sınıflandırılmamış olsa
        # bile ayna 'kopya' sayılır — aksi hâlde tek bir sabit üç kez
        # sayılır ve iş listesi şişer.
        #
        # AMA AKLAMA KAZANILIR (P10B4-08): kopya sayılmak için kanonikle
        # BİT-AYNI olmak gerekir. Eski sürüm yalnız "kanonik yaprak var mı"
        # diye bakıyordu; ölçülen karşı örnek: kanonik `.motor.thrust_n =
        # 5000.0` CANLI iken donmuş ve FARKLI değerli
        # `.trajectory.motor_data.thrust_n = 4200.0` yaprağı `kopya`
        # sınıfına düşüyor ve sınıflandırılmamış sayımından çıkıyordu —
        # oysa bit-aynı OLMAYAN ayna tam olarak "bayat/varsayılan kopya"
        # kusurudur. Ayrışan ayna artık aklanmaz: kendi kurallarıyla
        # sınıflandırılır ve gerekçesine ayrışma notu düşülür.
        for ayna, kanonik in AYNA_KOKLERI:
            if yol.startswith(ayna):
                kaynak = kanonik + yol[len(ayna):]
                if kaynak in yapraklar:
                    k_sinif = ilk.get(kaynak, ('?', ''))[0]
                    if shake.bit_ayni(yapraklar.get(yol),
                                      yapraklar.get(kaynak)):
                        sinif = 'kopya'
                        gerekce = (f'{kanonik.strip(".")} altindaki kanonik '
                                   f'kopyanin BIT-AYNI ikizi '
                                   f'(kanonik sinif: {k_sinif})')
                    else:
                        gerekce = (f'{gerekce} [AYNA AYRISIK: {kaynak} = '
                                   f'{yapraklar.get(kaynak)!r} ile bit-ayni '
                                   f'degil — kopya aklamasi UYGULANMADI]')
                        aklananlar.append({
                            'yol': yol, 'dal': 'ayna(ayrisik)',
                            'aklandi': False, 'kanonik': kaynak,
                            'deger': yapraklar.get(yol),
                            'kanonik_deger': yapraklar.get(kaynak)})
                break
        if sinif == 'beyanli_zayif':
            aklananlar.append({'yol': yol, 'dal': DAL_ZAYIF,
                               'aklandi': True, 'gerekce': gerekce})
        if sinif in ACIK_HESAP_SINIFLARI:
            acik_hesap.append({'yol': yol, 'sinif': sinif,
                               'gerekce': gerekce})
        kalemler.append((yol, sinif, gerekce))
        sayim[sinif] = sayim.get(sinif, 0) + 1
    # ``aklananlar``: sessiz kapatma yok — zayıf yolla kapanan ve kopya
    # aklaması REDDEDİLEN kalemler adlarıyla yayımlanır (P10B4-08).
    return {'sayim': sayim, 'kalemler': kalemler,
            'aklananlar': aklananlar, 'acik_hesap': acik_hesap}
