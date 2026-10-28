"""Şablon alan envanteri — bekçinin KATMAN A'sı.

Soru: "arayüzdeki her form alanı sunucuya gerçekten gönderiliyor mu?"

Bu, arka uç testlerinin GÖREMEDİĞİ bir kusur sınıfını yakalar. v2.6.25'te
hibritin ``chamber_material`` / ``wall_thickness`` / ``cooling_channels``
alanları için arka uç doğru yazılmıştı — HTTP katmanını test eden bir bekçi
"bağlandı" derdi. Ama ``advanced.html`` içindeki toplayıcı o üç alanı hiç
göndermiyordu; kullanıcı açısından üçü de ölüydü. Kusur arka uçta değil,
şablon ile payload arasındaki DİKİŞTEYDİ.

Bu modül yalnız statik metin okur (sunucu açmaz, hesap yapmaz), bu yüzden
milisaniyeler sürer ve her CI koşusunda çalışabilir.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Dict, List, Set

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / 'hrma/templates'

#: Sayfa -> (şablon dosyası, toplayıcı fonksiyon adı)
PAGES = {
    'hybrid': ('advanced.html', 'getFormData'),
    'solid': ('solid.html', 'collectAllParameters'),
    'liquid': ('liquid.html', 'collectAllParameters'),
}

#: Form alanı taşıyan etiketler.
_FIELD_TAG = re.compile(
    r'<(input|select|textarea)\b[^>]*\bid\s*=\s*["\']([\w-]+)["\']',
    re.I | re.S)

#: Salt gösterim/eylem amaçlı girdi tipleri — bunlar veri alanı değildir.
_NON_DATA_TYPES = {'button', 'submit', 'reset', 'file', 'search', 'image'}

_TYPE_ATTR = re.compile(r'\btype\s*=\s*["\']([\w-]+)["\']', re.I)

#: Toplayıcı içinde alan okuma biçimleri.
_READ_PATTERNS = (
    re.compile(r"getElementById\(\s*['\"]([\w-]+)['\"]"),
    re.compile(r"querySelector\(\s*['\"]#([\w-]+)['\"]"),
    re.compile(r"\bval\(\s*['\"]([\w-]+)['\"]"),      # yardımcı sarmalayıcılar
    re.compile(r"\bnumById\(\s*['\"]([\w-]+)['\"]"),
    re.compile(r"\bfieldValue\(\s*['\"]([\w-]+)['\"]"),
    # optNum: "boş bırakılırsa anahtar GÖNDERİLMEZ" okuyucusu (Faz 6 / T68,
    # solid.html paraşüt alanları). Diğer sarmalayıcılardan farkı, geçersiz
    # ya da boş değerde yedek sayı DÖNDÜRMEMESİDİR — çözücünün "verilmedi"
    # ile "değer geldi" ayrımını yapabilmesi buna bağlı. Okuma biçimi
    # açısından numById ile aynıdır: alanı id'siyle okur, dolayısıyla o
    # alanlar "hiçbir yerde okunmuyor" sayılmamalıdır.
    # ÖH D31 · arayuz-panel a3: ``liqOptNum`` / ``solOptNum`` da aynı
    # okuyucu sınıfıdır (ÖK-21 form katmanı sökümü; liquid.html ve
    # solid.html sayfa düzeyinde kendi sarmalayıcısını tanımlıyor, çünkü
    # ikisinde de işlev-kapsamlı bir ``optNum`` ZATEN var ve üst düzeyde
    # aynı adı tanımlamak GÖLGELEME üretirdi). Alan adı yine id ile
    # okunuyor; ön ek okuma biçimini değiştirmez.
    re.compile(r"\b\w*[Oo]ptNum\(\s*['\"]([\w-]+)['\"]"),
    # optChoice: optNum'un <select> karşılığı (2.6.27 yirminci parti,
    # liquid.html collectClosureAndFeedLineParams). Boş seçimde anahtar
    # gönderilmez; varsayılan kararı ve beyanı çözücünündür. Yerel takma
    # adla (choice) yazıldığında bu alanlar Katman A'da "hiçbir yerde
    # okunmuyor" görünmüştü — desen adı şablonla sözleşmelidir.
    re.compile(r"\boptChoice\(\s*['\"]([\w-]+)['\"]"),
    # enjAta: ÖH D32 · arayuz-panel a2 (OH-D31-14). advanced.html'in enjektör
    # kollarındaki okuyucu; gövdesi ``numById``dir, farkı boş alanda anahtarı
    # gövdeden SİLMESİDİR (``delete data[ad]``) — ÖK-21'in "kullanıcı
    # girmediyse alan GÖNDERİLMEZ" hükmü. Okuma biçimi açısından numById ile
    # aynı: alanı id'siyle okur, dolayısıyla o alanlar Katman A'da "hiçbir
    # yerde okunmuyor" sayılmamalıdır (optNum'un kendi gerekçesiyle birebir
    # aynı durum). Desen adı şablonla SÖZLEŞMEDİR: enjektör kollarında
    # yerel bir takma ad kullanılırsa alanlar yeniden görünmez olur.
    re.compile(r"\benjAta\(\s*['\"]([\w-]+)['\"]"),
)


@dataclass
class PageInventory:
    page: str
    template: str
    collector: str
    template_fields: Set[str]
    collected_fields: Set[str]
    #: Şablonda var, hiçbir toplayıcıda okunmuyor.
    uncollected: Set[str]

    def summary(self) -> str:
        return (f'{self.page}: sablonda {len(self.template_fields)} alan, '
                f'toplayicida {len(self.collected_fields)}, '
                f'toplanmayan {len(self.uncollected)}')


def _read(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding='utf-8')


def template_fields(html: str) -> Set[str]:
    """Şablondaki veri taşıyan form alanlarının id kümesi."""
    fields = set()
    for match in _FIELD_TAG.finditer(html):
        tag_text = html[match.start():match.end()]
        type_match = _TYPE_ATTR.search(tag_text)
        if type_match and type_match.group(1).lower() in _NON_DATA_TYPES:
            continue
        fields.add(match.group(2))
    return fields


def function_body(source: str, name: str) -> str:
    """Adı verilen JS fonksiyonunun gövdesini süslü parantez sayarak çıkarır.

    DİKKAT: aynı ada sahip BİRDEN FAZLA tanım varsa hepsi birleştirilir.
    Hibritte tam olarak bu durum yaşandı: ``app.js`` ve ``advanced.html``
    içinde iki ayrı ``getFormData`` vardı, inline olan diğerini gölgeliyordu
    ve envanter betiği yanlış kopyayı tarayınca 41 yerine 33 alan bulmuştu.
    """
    bodies = []
    for match in re.finditer(r'function\s+%s\s*\(' % re.escape(name), source):
        idx = source.index('{', match.end() - 1)
        depth = 0
        for pos in range(idx, len(source)):
            if source[pos] == '{':
                depth += 1
            elif source[pos] == '}':
                depth -= 1
                if depth == 0:
                    bodies.append(source[idx:pos + 1])
                    break
    return '\n'.join(bodies)


#: V3.0.5 T-ÇAPA-C1 — ADLI id LİSTESİ okuyucusu. V301/L-C (8ee59c845)
#: sıvı enjektör alanlarını ``(tip === 'pintle' ? LIQ_PINTLE_FIELDS :
#: LIQ_NOT_PINTLE_FIELDS).forEach(function (id) { … liqOptNum(id) … })``
#: ile okuyor: id literal değil, adlı dizi sabitinin elemanı. Okuma biçimi
#: optNum'un aynısıdır; liste adları ve elemanları şablonun kendisinden
#: çözülür (yalnız ``*_FIELDS`` adlı ``const`` diziler, yalnız ``OptNum(id)``
#: ile okunanlar — ``LIQ_CYCLE_UNREAD_FIELDS`` gibi OKUNMAYAN listeler
#: bu desene girmez).
_LIST_FOREACH_READ = re.compile(
    r"\(([^()]*?)\)\s*\.forEach\(\s*function\s*\(\s*(\w+)\s*\)\s*\{"
    r"[^{}]*?\b\w*[Oo]ptNum\(\s*\2\s*\)", re.S)
_FIELDS_CONST = r"const\s+%s\s*=\s*\[([^\]]*)\]"


def collected_fields(body: str, source: str = None) -> Set[str]:
    """Toplayıcı gövdesinde okunan alan id'leri.

    ``source`` verilirse (şablonun tamamı) adlı id listelerinin elemanları
    oradan çözülür; verilmezse ``body`` içinde aranır.
    """
    found: Set[str] = set()
    for pattern in _READ_PATTERNS:
        found.update(pattern.findall(body))
    kaynak = body if source is None else source
    for m in _LIST_FOREACH_READ.finditer(body):
        for ad in re.findall(r"\b([A-Z][A-Z0-9_]*_FIELDS)\b", m.group(1)):
            dizi = re.search(_FIELDS_CONST % re.escape(ad), kaynak)
            if dizi:
                found.update(re.findall(r"['\"]([\w-]+)['\"]", dizi.group(1)))
    return found


def build(page: str) -> PageInventory:
    template, collector = PAGES[page]
    html = _read(template)
    fields = template_fields(html)
    body = function_body(html, collector)
    if not body:
        raise AssertionError(
            f"{template} icinde '{collector}' toplayicisi bulunamadi")
    # Toplayıcının çağırdığı yardımcılar da sayılır: bazı sayfalar alanları
    # alt fonksiyonlarda okuyor. Bu yüzden ŞABLONUN TAMAMINDAKİ okumalar da
    # toplanır, ama toplayıcı gövdesi ayrıca raporlanır.
    read_anywhere = collected_fields(html)
    read_in_collector = collected_fields(body)
    return PageInventory(
        page=page,
        template=template,
        collector=collector,
        template_fields=fields,
        collected_fields=read_in_collector,
        uncollected=fields - read_anywhere,
    )


def build_all() -> Dict[str, PageInventory]:
    return {page: build(page) for page in PAGES}


# ---------------------------------------------------------------------------
# KATMAN B için alan tanımları — şablonun KENDİ min/max/options değerlerinden
# ---------------------------------------------------------------------------
#
# Sarsım aralığını elle bir listede tutmak iki yönden çürür: yeni alan
# eklenince listeye girmez (sessizce ölçülmez), mevcut alanın aralığı
# değişince liste eskir ve alan YALANCI ÖLÜ görünür (aralık dışına sarsılan
# değer motor tarafından reddedilir).
#
# Bu yüzden aralık, arayüzün kendisinden okunur: ``min``/``max`` öznitelikleri
# zaten kullanıcıya dayatılan sözleşmedir, dolayısıyla motorun kabul ettiği
# aralığın doğal üst kümesidir.

_ATTR = {
    'min': re.compile(r'\bmin\s*=\s*["\']([^"\']+)["\']', re.I),
    'max': re.compile(r'\bmax\s*=\s*["\']([^"\']+)["\']', re.I),
    'value': re.compile(r'\bvalue\s*=\s*["\']([^"\']*)["\']', re.I),
    'type': _TYPE_ATTR,
}
_OPTION = re.compile(r'<option\b[^>]*\bvalue\s*=\s*["\']([^"\']*)["\']', re.I)
_TAG_OPEN = re.compile(
    r'<(input|select|textarea)\b[^>]*\bid\s*=\s*["\']%s["\'][^>]*>', re.I)


@dataclass
class TemplateField:
    """Şablondan okunan bir form alanının sarsım için gereken bilgisi."""
    field_id: str
    tag: str                      # input | select | textarea
    input_type: str = ''          # number | text | checkbox | ...
    minimum: float = None
    maximum: float = None
    default: str = ''
    options: List[str] = None

    @property
    def kind(self) -> str:
        if self.tag == 'select':
            return 'choice'
        if self.input_type == 'checkbox':
            return 'bool'
        return 'number' if self.input_type in ('number', 'range') else 'text'


def _as_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


#: v3.0.1 kulvar M — sunucu kaydından basılan seçici seçenekleri. Hibrit
#: sayfasının malzeme seçicileri seçeneklerini şablonda elle yazmaz; şablon
#: başındaki ``malzeme_secenekleri`` makrosu sunucunun kaydını döker
#: (app.py ``_hibrit_malzeme_secim_kaydi``). Ham metinde ``<option`` yoktur;
#: seçenekler aynı kayıttan, sayfanın basacağı sırayla okunur. Üçüncü
#: argüman ``true`` ise makro önce boş ("seçilmedi") seçeneği basar.
_SUNUCU_SECENEK_MAKROSU = re.compile(
    r'\{\{\s*malzeme_secenekleri\(\s*hybrid_materials\.(\w+)\s*,[^}]*?'
    r'(,\s*true\s*)?\)\s*\}\}')


def _sunucu_secenekleri(govde: str) -> List[str]:
    m = _SUNUCU_SECENEK_MAKROSU.search(govde)
    if not m:
        return []
    from hrma.app import _hibrit_malzeme_secim_kaydi
    rol = _hibrit_malzeme_secim_kaydi()[m.group(1)]
    return ([''] if m.group(2) else []) + [o['value'] for o in rol['options']]


#: V301/K-B — katı sayfasının kasa/lüle seçicileri de seçeneklerini sunucu
#: kaydından basar (``solid_materials.<alan>.options`` Jinja döngüsü; ham
#: metindeki tek ``<option value="{{ o.value }}">`` bir ŞABLON ifadesidir,
#: seçenek değil). Seçenekler aynı kayıttan, sayfanın basacağı sırayla.
_KATI_SUNUCU_SECENEK = re.compile(r'solid_materials\.(\w+)\.options')


def _kati_sunucu_secenekleri(govde: str):
    m = _KATI_SUNUCU_SECENEK.search(govde)
    if not m:
        return None
    from hrma.engines.solid_rocket_engine import solid_material_options
    return [o['value'] for o in solid_material_options(m.group(1))]


#: V301/L-D (SV-12) — sıvı sayfasının kamara malzemesi seçicisi de
#: seçeneklerini sunucu kaydından basar (``liquid_form.<alan>.options``;
#: app.py ``_sivi_form_kaydi`` <- motorun ``CHAMBER_MATERIAL_MAP``i).
_SIVI_SUNUCU_SECENEK = re.compile(r'liquid_form\.(\w+)\.options')


def _sivi_sunucu_secenekleri(govde: str):
    m = _SIVI_SUNUCU_SECENEK.search(govde)
    if not m:
        return None
    from hrma.app import _sivi_form_kaydi
    return [o['value'] for o in _sivi_form_kaydi()[m.group(1)]['options']]


def field_specs(html: str) -> Dict[str, TemplateField]:
    """Şablondaki her form alanı için tip, aralık, varsayılan ve seçenekler."""
    out: Dict[str, TemplateField] = {}
    for match in _FIELD_TAG.finditer(html):
        tag = match.group(1).lower()
        field_id = match.group(2)
        # Etiketin tamamını al (kapanışa kadar) — öznitelikler orada.
        open_tag = _TAG_OPEN.search(html, max(0, match.start() - 200))
        tag_text = open_tag.group(0) if (
            open_tag and f'"{field_id}"' in open_tag.group(0)
            or open_tag and f"'{field_id}'" in open_tag.group(0)) else html[
                match.start():html.find('>', match.start()) + 1]

        type_match = _ATTR['type'].search(tag_text)
        input_type = type_match.group(1).lower() if type_match else ''
        if input_type in _NON_DATA_TYPES:
            continue

        options: List[str] = []
        if tag == 'select':
            end = html.find('</select>', match.start())
            if end != -1:
                govde = html[match.start():end]
                options = _kati_sunucu_secenekleri(govde)
                if options is None:
                    options = _sivi_sunucu_secenekleri(govde)
                if options is None:
                    options = _OPTION.findall(govde)
                if not options:
                    options = _sunucu_secenekleri(govde)

        value_match = _ATTR['value'].search(tag_text)
        out[field_id] = TemplateField(
            field_id=field_id,
            tag=tag,
            input_type=input_type,
            minimum=_as_float(
                _ATTR['min'].search(tag_text).group(1)
                if _ATTR['min'].search(tag_text) else None),
            maximum=_as_float(
                _ATTR['max'].search(tag_text).group(1)
                if _ATTR['max'].search(tag_text) else None),
            default=value_match.group(1) if value_match else '',
            options=options,
        )
    return out


def field_specs_for(page: str) -> Dict[str, TemplateField]:
    template, _ = PAGES[page]
    return field_specs(_read(template))
