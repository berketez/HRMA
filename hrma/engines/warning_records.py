"""Uyarı kaydı yardımcıları — TEK TANIM NOKTASI.

ÖH D30 · katı a1 · OH-Z3-04 (kalan ayak). Bu modül, motor katmanlarının
paylaştığı uyarı-kaydı sözleşmesinin tek tanım noktasıdır.

NEDEN VAR (ölçüldü, docs/scofield/raw/OH/D30/kati/a1/once.json · K2):
``_warning_identity`` İKİ motor dosyasında (``solid_rocket_engine.py`` ve
``hybrid_rocket_engine.py``) birebir aynı gövdeyle iki kez yazılıydı ve
her ikisinin docstring'i "sözleşme öbürüyle BİREBİR aynıdır" diye NOTLA
bağlıydı — yani eşitlik yorumla korunuyordu, kodla değil. Ölçülen durum:
``tanim_toplam = 2``, ``iki_motor_ayni_nesne = False``. Defterin andığı
üçüncü kopya (``templates/solid.html``) D29'da ölçülüp çürütülmüştü;
şablondaki ``warningIdentity`` AYNI ada sahip değildir ve JS aynasıdır
(aşağıya bakınız).

CLAUDE.md kural 11 / Doktrin 4: aynı sözleşme iki yerde yazılmaz. Kopyanın
riski akademik değildir — kimlik anahtarı yinelenen uyarıları ELEYEN
ölçüttür; iki kopya birbirinden AYRIŞIRSA aynı hüküm kullanıcıya iki kez
basılır ya da (daha kötüsü) bir kritik hüküm yanlışlıkla elenir.

JS AYNASI (bilinçli, tek kaynak DEĞİL): tarayıcı tarafında AYNI eleme
ölçütünü ``templates/solid.html`` içindeki ``warningIdentity``
(``displaySolidWarnings``) kurar — ölçüldü, depoda tek JS aynası odur.
Anahtarın DİZGESİ iki tarafta aynı değildir (Python ``repr`` imzası, JS
``k=v`` birleşimi) ve olması da gerekmez: her taraf kendi listesini kendi
içinde eler. Ortak olan SÖZLEŞMEdir — kimlik koddan, ciddiyetten ve
parametre kümesinden kurulur, parametre SIRASINDAN değil, ve kaydın metin
alanları kimliğe girmez. Python tarafı bu sözleşmeyi değiştirirse şablon
aynası da güncellenmelidir; bekçisi ``tests/test_d30_kati_a1.py``.
"""


def warning_identity(record):
    """Bir uyarı kaydının TEKİLLİK anahtarı (yinelenmeyi önlemek için).

    Aynı hüküm birden fazla blokta yayımlanabilir (ör. ısı transferi
    modülünde ``gas_side_analysis.warnings`` kayıtları ``safety_analysis``
    içine de kopyalanır). Teslim kanalı bu kayıtları topladığında kullanıcı
    aynı cümleyi iki kez görmemelidir; ama kaydın KENDİSİ de değişmemelidir.
    Bu yüzden metin değil, kaydın kimliği (kod + ciddiyet + parametreler)
    karşılaştırılır.

    Anahtarın şekli (sözleşme): ``"<code>|<severity>|<params imzası>"``.
    ``params`` bir sözlükse anahtarları sıralanıp ``(str(k), repr(v))``
    çiftleri olarak imzalanır — sözlük SIRASI anahtarı değiştirmez. Kayıt
    sözlük değilse ``"str:<kayıt>"`` döner (düz metin uyarı kanalı).

    Kaydın ``fallback`` (İngilizce yedek metin) gibi ek alanları kimliğe
    GİRMEZ: aynı hüküm, metni taşıyıp taşımamasına göre iki kez basılmaz.
    """
    if isinstance(record, dict):
        params = record.get('params')
        if isinstance(params, dict):
            imza = repr(sorted((str(k), repr(v)) for k, v in params.items()))
        else:
            imza = repr(params)
        return f"{record.get('code')}|{record.get('severity')}|{imza}"
    return f'str:{record}'


def json_native_params(params):
    """Uyarı parametrelerini JSON'un KENDİ tiplerine indirger.

    ÖH D32 fix-35d · taban ``dd1dcddc`` kırmızısı
    ``tests/test_hibrit_beyan_a10.py::test_sonuc_json_serilestirilebilir``.

    ÖLÇÜLDÜ (``hibrit_once.json``): hibrit ``design_warnings[0]``
    (``warn.hybrid.htpb_coeff_bias``) dört parametreyi PYTHON DEMETİ olarak
    yayımlıyordu — ``campaign_oxidizer_scope``,
    ``independent_campaign_bias_band_pct``, ``independent_campaigns``,
    ``unreconciled_reasons``. JSON'da demet YOKTUR: ``json.dumps`` onları
    diziye çevirir, ``json.loads`` liste olarak geri verir, yani yayımlanan
    gövde ile istemcinin okuduğu gövde AYNI NESNE DEĞİLDİR. Gidiş-dönüş
    bekçisi (``tests/support/serilestirme.py``) bunu yakaladı.

    Kusur akademik değildir: aynı kayıt ``app.py``de
    ``json.dumps(entry['params'], sort_keys=True, ...)`` ile de yayımlanıyor
    ve uyarının TEKİLLİK anahtarı (:func:`warning_identity`) parametrelerin
    ``repr``inden kuruluyor — ``('n2o',)`` ile ``['n2o']`` farklı imzalardır.
    Yani aynı hüküm, gidiş-dönüşün hangi tarafında üretildiğine göre iki
    ayrı kimlik alabilirdi.

    SAYI DEĞİŞTİRMEZ, ALAN EKLEMEZ, ALAN SİLMEZ: yalnız kap tipini
    (``tuple``/``set``/``frozenset`` -> ``list``) JSON'un kendi kabına
    indirger ve sözlük anahtarlarını dize yapar. ``set`` sıralanır, çünkü
    küme sırasız olduğu hâlde liste sıralıdır; sıralamasız bir dönüşüm
    koşumdan koşuma değişen bir gövde üretirdi.

    Katı/sıvı motor ``_w``leri de bu kapıyı kullanabilir (sözleşme aynı);
    bugün ölçülen demet yalnız hibrit tarafındadır, o yüzden yalnız o
    bağlandı — ölçülmemiş bir yüzey "her ihtimale karşı" değiştirilmez.
    """
    return {str(ad): _json_yerli(deger) for ad, deger in (params or {}).items()}


def _json_yerli(deger):
    """``json_native_params`` için özyinelemeli kap indirgemesi."""
    if isinstance(deger, dict):
        return {str(k): _json_yerli(v) for k, v in deger.items()}
    if isinstance(deger, (set, frozenset)):
        return [_json_yerli(v) for v in sorted(deger, key=repr)]
    if isinstance(deger, (list, tuple)):
        return [_json_yerli(v) for v in deger]
    return deger
