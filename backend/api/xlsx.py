"""
极简 XLSX 生成器（第 43 批）

背景：后端运行环境（crop_env）里**没有** openpyxl / xlsxwriter，
只有 pandas（而没有引擎时 pandas 也写不了 xlsx）。
为了"导出 Excel"不引入新依赖、也不要求联网安装，这里用标准库
`zipfile` + XML 手写一个最小可用的 xlsx（Office / WPS / LibreOffice 都能打开）。

一个 xlsx 本质是个 zip，最少需要这几个部件：
    [Content_Types].xml
    _rels/.rels
    xl/workbook.xml
    xl/_rels/workbook.xml.rels
    xl/worksheets/sheet1.xml

字符串用 `inlineStr`（省掉 sharedStrings 表），数字/日期直接写 `<v>`。

校验：本文件生成的产物已用 base anaconda 里的 openpyxl 3.1.5 实际打开并读取过单元格。
"""
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape
import zipfile

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

#: 两个样式：0=普通，1=表头（加粗 + 灰底 + 边框）
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><name val="\u5fae\u8f6f\u96c5\u9ed1"/></font>
<font><b/><sz val="11"/><name val="\u5fae\u8f6f\u96c5\u9ed1"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEAF5EF"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFE3CD"/></left><right style="thin"><color rgb="FFBFE3CD"/></right><top style="thin"><color rgb="FFBFE3CD"/></top><bottom style="thin"><color rgb="FFBFE3CD"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _column_name(index):
    """0 → A, 25 → Z, 26 → AA"""
    name = ''
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell(ref, value, style_index=0):
    """生成一个单元格；字符串走 inlineStr，数字走 v"""
    if value is None or value == '':
        return f'<c r="{ref}" s="{style_index}"/>'

    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style_index}" t="b"><v>{1 if value else 0}</v></c>'

    if isinstance(value, (int, float)):
        return f'<c r="{ref}" s="{style_index}"><v>{value}</v></c>'

    if isinstance(value, (datetime, date)):
        text = value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(value, datetime) else value.isoformat()
        return (f'<c r="{ref}" s="{style_index}" t="inlineStr">'
                f'<is><t xml:space="preserve">{escape(text)}</t></is></c>')

    text = escape(str(value))
    return f'<c r="{ref}" s="{style_index}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(headers, rows, column_widths=None):
    """生成 sheet1.xml（表头样式 + 冻结首行 + 自动筛选 + 列宽）"""
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']

    if column_widths:
        parts.append('<cols>')
        for index, width in enumerate(column_widths):
            col = _column_name(index)
            parts.append(f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"/>')
        parts.append('</cols>')

    parts.append(f'<sheetData>')

    # 表头
    parts.append('<row r="1">')
    for index, header in enumerate(headers):
        parts.append(_cell(f'{_column_name(index)}1', header, style_index=1))
    parts.append('</row>')

    # 数据
    for row_index, row in enumerate(rows, start=2):
        parts.append(f'<row r="{row_index}">')
        for col_index, value in enumerate(row):
            parts.append(_cell(f'{_column_name(col_index)}{row_index}', value))
        parts.append('</row>')

    parts.append('</sheetData>')
    # 冻结首行 + 给表头加自动筛选（打开就能直接筛）
    parts.append('<autoFilter ref="A1:%s%d"/>' % (_column_name(len(headers) - 1), len(rows) + 1))
    parts.append('<sheetViews><sheetView workbookViewId="0">'
                 '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                 '</sheetView></sheetViews>')
    parts.append('</worksheet>')
    return ''.join(parts)


def build_workbook(headers, rows, sheet_name='Sheet1', column_widths=None):
    """
    生成 xlsx 的字节内容

    :param headers: 表头列表
    :param rows: 二维可迭代（每行长度应与表头一致）
    :param sheet_name: 工作表名
    :param column_widths: 每列宽度（可选）
    """
    if not headers:
        raise ValueError('表头不能为空')

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', CONTENT_TYPES)
        archive.writestr('_rels/.rels', ROOT_RELS)
        archive.writestr('xl/workbook.xml',
                         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                         '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                         f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
                         '</workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', WORKBOOK_RELS)
        archive.writestr('xl/styles.xml', STYLES)
        archive.writestr('xl/worksheets/sheet1.xml', _sheet_xml(headers, rows, column_widths))

    return buffer.getvalue()


# ============================================================================
# 第 44 批：读取表格（病害批量导入用）
# ----------------------------------------------------------------------------
# 同样不引入依赖：xlsx 就是 zip + XML，用标准库解出来即可。
# 支持：
#   · .xlsx（读第一个工作表，处理 sharedStrings / inlineStr / 数字 / 布尔）
#   · .csv（兼容 UTF-8 BOM 与 GBK，分隔符自动识别 , ; \t）
# ============================================================================
import csv
import io
import re

MAIN_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
CELL_REF_RE = re.compile(r'^([A-Z]+)')


def column_index(ref):
    """把单元格引用（如 "AB12"）里的列字母转成 0 基下标"""
    match = CELL_REF_RE.match(ref or '')
    if not match:
        return None
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _shared_strings(archive):
    """解析 xl/sharedStrings.xml，返回字符串列表"""
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    import xml.etree.ElementTree as ET

    root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    values = []
    for si in root.findall(f'{MAIN_NS}si'):
        # 一个 <si> 可能由多个 <r><t> 片段组成（富文本），全部拼起来
        pieces = [node.text or '' for node in si.iter(f'{MAIN_NS}t')]
        values.append(''.join(pieces))
    return values


def read_xlsx_rows(content):
    """
    读取 xlsx 第一个工作表，返回二维字符串列表

    说明：空单元格不会出现在 XML 里，这里按 `r` 属性里的列号补齐，
    避免"中间空一列导致整行左移"这种最坑人的解析错误。
    """
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        sheet_name = 'xl/worksheets/sheet1.xml'
        if sheet_name not in names:
            sheets = sorted(name for name in names if name.startswith('xl/worksheets/') and name.endswith('.xml'))
            if not sheets:
                raise ValueError('xlsx 里没有找到工作表')
            sheet_name = sheets[0]

        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(sheet_name))

    rows = []
    for row_node in root.iter(f'{MAIN_NS}row'):
        cells = {}
        for cell in row_node.findall(f'{MAIN_NS}c'):
            index = column_index(cell.get('r'))
            if index is None:
                index = len(cells)
            cell_type = cell.get('t')

            if cell_type == 'inlineStr':
                text = ''.join(node.text or '' for node in cell.iter(f'{MAIN_NS}t'))
            else:
                value_node = cell.find(f'{MAIN_NS}v')
                raw = value_node.text if value_node is not None and value_node.text is not None else ''
                if cell_type == 's' and raw.isdigit():
                    position = int(raw)
                    text = shared[position] if 0 <= position < len(shared) else ''
                elif cell_type == 'b':
                    text = '是' if raw == '1' else '否'
                else:
                    text = raw
            cells[index] = (text or '').strip()

        width = (max(cells) + 1) if cells else 0
        rows.append([cells.get(i, '') for i in range(width)])

    # 去掉整行为空的（Excel 里常见的"幽灵空行"）
    return [row for row in rows if any(cell for cell in row)]


def read_csv_rows(content):
    """读取 csv（自动尝试 utf-8-sig / utf-8 / gbk，并嗅探分隔符）"""
    text = None
    for encoding in ('utf-8-sig', 'utf-8', 'gbk', 'latin-1'):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError('无法识别文件编码，请另存为 UTF-8 或 CSV 后重试')

    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ','

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [[(cell or '').strip() for cell in row] for row in reader]
    return [row for row in rows if any(cell for cell in row)]


def parse_table(filename, content):
    """按扩展名分派解析，返回二维字符串列表"""
    name = (filename or '').lower()
    if name.endswith('.xlsx') or name.endswith('.xlsm'):
        return read_xlsx_rows(content)
    if name.endswith('.csv') or name.endswith('.txt'):
        return read_csv_rows(content)
    raise ValueError('只支持 .xlsx 或 .csv 文件')
