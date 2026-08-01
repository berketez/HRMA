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
``SINIFLANDIRILMAMIS``  Yukarıdakilerden hiçbiri. Bakılacak yer.

Kural sırası önemlidir: ``beyanli`` en sona konmaz, çünkü bir ızgara noktası
da beyan taşıyabilir; en açıklayıcı sınıf kazanır.
"""

from __future__ import annotations

import re

#: Kardeş açıklama alanı sonekleri — projenin her yerinde kullanılan sözleşme.
BEYAN_SONEKLERI = ('_basis', '_source', '_status', '_definition', '_note',
                   '_model', '_reason', '_assumption',
                   # v2.6.26 — projede fiilen kullanilan ama listede olmayan
                   # sonekler (olculdu): hedef/gerceklenen ciftleri, yuk
                   # boyutlandirma bayragi, yontem adi, varsayim bayragi.
                   '_is_target', '_load_sized', '_method', '_assumed',
                   '_available', '_tautological', '_labels')

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
    """Ad sonundaki birim jetonunu soyar (varsa)."""
    dusuk = ad.lower()
    for sonek in BIRIM_SONEKLERI:
        if dusuk.endswith(sonek) and len(dusuk) > len(sonek):
            return ad[: -len(sonek)]
    return ad


def _jetonlar(ad: str) -> set:
    """Yaprak adını sözcüklere ayırır (beyan metniyle eşleştirmek için).

    Eşik 2: kimyasal element simgeleri (``AL``, ``C``, ``N``) iki harflidir ve
    3 harf eşiğiyle hiç jeton üretmiyorlardı — beyan metni alanı anmasına
    rağmen eşleşme kurulamıyordu.
    """
    # Rakam iceren jetonlar SOZCUK degil, birim/indeks artigidir
    # (`grain_thermal_expansion_1k` -> '1k'); beyan metninde gecmezler
    # ve eslesmeyi haksiz yere bozarlar.
    return {j for j in re.split(r'[_\W]+', ad.lower())
            if len(j) >= 2 and j.isalpha()}


def _kardes_beyan_var(yol: str, yapraklar: dict) -> str | None:
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

    # 1 + 2: doğrudan ve birimsiz kardeş
    for taban in (yol, ust + '.' + _birimsiz(ad)):
        for sonek in BEYAN_SONEKLERI:
            if (taban + sonek) in yapraklar:
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
                    return kardes

    # 4: paralel blok `a.b_source.c`
    if '.' in ust.lstrip('.'):
        kok, blok = ust.rsplit('.', 1)
        for sonek in ('_source', '_basis', '_status', '_source_labels'):
            aday = f'{kok}.{blok}{sonek}.{ad}'
            if aday in yapraklar:
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
            if son not in ('basis', 'status', 'source', 'model', 'method',
                           'assumptions', 'model_note', 'model_limitation') \
                    and not son.endswith('_basis'):
                continue
            metin = str(deger or '').lower()
            if hedef and hedef.issubset(_jetonlar(metin)):
                return anahtar
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
                    return anahtar
    return None


def siniflandir(yol: str, deger, yapraklar: dict) -> tuple[str, str]:
    """Tek yaprağı sınıflandırır. Döner: (sınıf, gerekçe)."""
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
                       'acceleration', 'range')
            and isinstance(deger, (int, float)) and not isinstance(deger, bool)
            and abs(float(deger)) < 1e-12):
        return 'tanim', 'integrasyon baslangic kosulu (faz-yerel t=0)'

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
        if abs(float(deger) - 1.0) < 1e-12 and ('ratio' in ad or ad.endswith('_ratio')):
            return 'tanim', 'referans noktasina normalize edilmis oran (=1.0)'
    if ad == 'step' or ad == 'index':
        return 'tanim', 'sira numarasi / ordinal'

    # 4) Beyanlı — cozucu durumu aciklamis
    beyan = _kardes_beyan_var(yol, yapraklar)
    if beyan is not None:
        return 'beyanli', f'kardes aciklama alani: {beyan.rsplit(".", 1)[-1]}'
    if deger is None:
        return 'beyanli', 'deger uretilmedi (None) — modellenmedigi bildirilmis'

    return 'SINIFLANDIRILMAMIS', 'neden sabit oldugu bilinmiyor'


#: Aynı sözlüğün yanıtta ikinci/üçüncü kez yayımlandığı kökler.
#: app.py motor sonucunu hem `.motor` altına, hem OpenRocket dalına, hem de
#: yörünge dalına koyuyor — birebir AYNI nesne. Bu yapraklar ayrı bir bulgu
#: değildir; kanonik kopyanın sınıfını miras alırlar. Aksi hâlde tek bir
#: sabit üç kez sayılıyor ve "sınıflandırılmamış" rakamı şişiyor.
AYNA_KOKLERI = (
    ('.openrocket.flight_profile.motor_data.', '.motor.'),
    ('.trajectory.motor_data.', '.motor.'),
    # v2.6.26 — olculdu, dordu de birebir ikiz (19/19, 9/9, 10/10, 4/4):
    # app.py ust duzey kisayollar da yayimliyor.
    ('.design_summary.', '.motor.design_summary.'),
    ('.grain_design.', '.motor.grain_design.'),
    ('.injector_design.', '.motor.injector_design.'),
    ('.nozzle_angles.', '.motor.nozzle_angles.'),
    ('.motor_geometry.nozzle_angles.', '.nozzle_angles.'),
)


def siniflandir_hepsi(sabit_yollar, yapraklar: dict) -> dict:
    """Sabit yaprak listesini sınıflandırır.

    Döner: {'sayim': {sınıf: adet}, 'kalemler': [(yol, sınıf, gerekçe), ...]}
    """
    yollar = list(sabit_yollar)
    ilk: dict[str, tuple[str, str]] = {}
    for yol in yollar:
        ilk[yol] = siniflandir(yol, yapraklar.get(yol), yapraklar)

    kalemler = []
    sayim: dict[str, int] = {}
    for yol in yollar:
        sinif, gerekce = ilk[yol]
        # Ayna kökündeki yaprak AYRI BİR İŞ DEĞİLDİR: kanonik kopya
        # düzeltilince o da düzelir. Kanonik henüz sınıflandırılmamış olsa
        # bile ayna 'kopya' sayılır — aksi hâlde tek bir sabit üç kez
        # sayılır ve iş listesi şişer.
        for ayna, kanonik in AYNA_KOKLERI:
            if yol.startswith(ayna):
                kaynak = kanonik + yol[len(ayna):]
                if kaynak in yapraklar:
                    k_sinif = ilk.get(kaynak, ('?', ''))[0]
                    sinif = 'kopya'
                    gerekce = (f'{kanonik.strip(".")} altindaki kanonik '
                               f'kopyanin ikizi (kanonik sinif: {k_sinif})')
                break
        kalemler.append((yol, sinif, gerekce))
        sayim[sinif] = sayim.get(sinif, 0) + 1
    return {'sayim': sayim, 'kalemler': kalemler}
