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


def collected_fields(body: str) -> Set[str]:
    """Toplayıcı gövdesinde okunan alan id'leri."""
    found: Set[str] = set()
    for pattern in _READ_PATTERNS:
        found.update(pattern.findall(body))
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
                options = _OPTION.findall(html[match.start():end])

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
