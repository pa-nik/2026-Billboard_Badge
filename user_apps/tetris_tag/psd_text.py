"""Live text layers for the layered Photoshop file made by make_faberrgen_psd.py.

psd-tools reads text layers but cannot make them, so this builds the "type tool" block of a
layer (the text, its fonts and sizes, the colour, where it starts) by hand. The layer also
keeps the pixels of the text, so an editor that does not read the block still shows the
right picture; an editor that does shows editable text in the named fonts.

Run on your computer, not on the badge. Needs psd-tools.
"""

from psd_tools.constants import Compression
from psd_tools.api.layers import PixelLayer
from psd_tools.psd.descriptor import (Bool, Descriptor, DescriptorBlock, Double, Enumerated, Integer,
                                      RawData, String, Unit, UnitFloat)
from psd_tools.psd.tagged_blocks import Tag, TaggedBlock, TypeToolObjectSetting


# --- the engine data: the text's own mini file format (nested << >> dictionaries) -------------

def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    raise TypeError(v)


def _string(text):
    """A string in UTF-16 with a byte order mark. The bytes for ( ) and \\ get a backslash in
    front of them (byte by byte, the way psd-tools writes and reads them)."""
    data = text.encode("utf-16-be")
    for byte in (b"\\", b"(", b")"):
        data = data.replace(byte, b"\\" + byte)
    return b"(\xfe\xff" + data + b")"


def _write(v, depth, out):
    """Append value v (dict, list, str, number, bool) to out, the way Photoshop lays it out."""
    pad = b"\t" * depth
    if isinstance(v, dict):
        out.append(b"<<\n")
        for key, item in v.items():
            out.append(pad + b"\t/" + key.encode() + b" ")
            if isinstance(item, dict):
                out.append(b"\n" + pad + b"\t")
            _write(item, depth + 1, out)
            out.append(b"\n")
        out.append(pad + b">>")
    elif isinstance(v, list):
        if all(not isinstance(i, (dict, list)) for i in v):
            out.append(b"[ " + b" ".join(_scalar(i).encode() for i in v) + b" ]")
        else:
            out.append(b"[\n")
            for item in v:
                out.append(pad + b"\t")
                _write(item, depth + 1, out)
                out.append(b"\n")
            out.append(pad + b"]")
    elif isinstance(v, str):
        out.append(_string(v))
    else:
        out.append(_scalar(v).encode())


def engine_bytes(data):
    out = [b"\n\n"]
    _write(data, 0, out)
    return b"".join(out)


def _style(font_index, size, colour, leading=None, faux_bold=False):
    return {
        "Font": font_index, "FontSize": float(size), "FauxBold": faux_bold, "FauxItalic": False,
        "AutoLeading": leading is None, "Leading": float(leading or 0), "HorizontalScale": 1.0,
        "VerticalScale": 1.0, "Tracking": 0, "AutoKerning": True, "Kerning": 0, "BaselineShift": 0.0,
        "FontCaps": 0, "FontBaseline": 0, "Underline": False, "Strikethrough": False, "Ligatures": True,
        "DLigatures": False, "BaselineDirection": 2, "Tsume": 0.0, "StyleRunAlignment": 2, "Language": 0,
        "NoBreak": False, "FillColor": {"Type": 1, "Values": [1.0] + [float(c) for c in colour]},
        "StrokeColor": {"Type": 1, "Values": [1.0, 0.0, 0.0, 0.0]}, "FillFlag": True, "StrokeFlag": False,
        "FillFirst": True, "YUnderline": 1, "OutlineWidth": 1.0, "CharacterDirection": 0,
        "HindiNumbers": False, "Kashida": 1, "DiacriticPos": 2,
    }


def _paragraph():
    return {"Justification": 0, "FirstLineIndent": 0.0, "StartIndent": 0.0, "EndIndent": 0.0,
            "SpaceBefore": 0.0, "SpaceAfter": 0.0, "AutoHyphenate": True, "HyphenatedWordSize": 6,
            "PreHyphen": 2, "PostHyphen": 2, "ConsecutiveHyphens": 8, "Zone": 36.0,
            "WordSpacing": [0.8, 1.0, 1.33], "LetterSpacing": [0.0, 0.0, 0.0],
            "GlyphSpacing": [1.0, 1.0, 1.0], "AutoLeading": 1.2, "LeadingType": 0, "Hanging": False,
            "Burasagari": False, "KinsokuOrder": 0, "EveryLineComposer": False}


def engine_data(paragraphs, fonts, colour, x, y):
    """paragraphs: [[(text, font name, size, faux bold), ...], ...], one list per line (each
    ends up as a paragraph); fonts: PostScript names; colour: (r, g, b) 0..1; (x, y) the
    start of the first baseline. Returns the engine data as bytes."""
    runs, lengths, para_lengths = [], [], []
    for p, line in enumerate(paragraphs):
        total = 0
        for k, (text, font, size, bold, leading) in enumerate(line):
            last = k == len(line) - 1
            text = text + ("\r" if last else "")  # a paragraph ends with a carriage return
            runs.append({"StyleSheet": {"StyleSheetData": _style(fonts.index(font), size, colour, leading, bold)}})
            lengths.append(len(text))
            total += len(text)
        para_lengths.append(total)
    full = "".join(t + ("\r" if k == len(line) - 1 else "")
                   for line in paragraphs for k, (t, *_r) in enumerate(line))
    resources = {
        "KinsokuSet": [{"Name": "PhotoshopKinsokuHard", "NoStart": "", "NoEnd": "", "Keep": "", "Hanging": ""},
                       {"Name": "PhotoshopKinsokuSoft", "NoStart": "", "NoEnd": "", "Keep": "", "Hanging": ""}],
        "MojiKumiSet": [{"InternalName": "Photoshop6MojiKumiSet%d" % i} for i in range(1, 5)],
        "TheNormalStyleSheet": 0, "TheNormalParagraphSheet": 0,
        "ParagraphSheetSet": [{"Name": "Normal RGB", "DefaultStyleSheet": 0, "Properties": _paragraph()}],
        "StyleSheetSet": [{"Name": "Normal RGB", "StyleSheetData": _style(0, 12, (0, 0, 0))}],
        "FontSet": [{"Name": f, "Script": 0, "FontType": 1, "Synthetic": 0} for f in fonts],
        "SuperscriptSize": 0.583, "SuperscriptPosition": 0.333, "SubscriptSize": 0.583,
        "SubscriptPosition": -0.333, "SmallCapSize": 0.7,
    }
    adjustments = {"Axis": [1.0, 0.0, 1.0], "XY": [0.0, 0.0]}
    engine = {
        "Editor": {"Text": full},
        "ParagraphRun": {
            "DefaultRunData": {"ParagraphSheet": {"DefaultStyleSheet": 0, "Properties": {}},
                               "Adjustments": adjustments},
            "RunArray": [{"ParagraphSheet": {"DefaultStyleSheet": 0, "Properties": _paragraph()},
                          "Adjustments": adjustments} for _ in paragraphs],
            "RunLengthArray": para_lengths, "IsJoinable": 1},
        "StyleRun": {
            "DefaultRunData": {"StyleSheet": {"StyleSheetData": {}}},
            "RunArray": runs, "RunLengthArray": lengths, "IsJoinable": 2},
        "GridInfo": {"GridIsOn": False, "ShowGrid": False, "GridSize": 18.0, "GridLeading": 22.0,
                     "GridColor": {"Type": 1, "Values": [0.0, 0.0, 0.0, 1.0]},
                     "GridLeadingFillColor": {"Type": 1, "Values": [0.0, 0.0, 0.0, 1.0]},
                     "AlignLineHeightToGridFlags": False},
        "AntiAlias": 4, "UseFractionalGlyphWidths": True,
        "Rendered": {"Version": 1, "Shapes": {"WritingDirection": 0, "Children": [
            {"ShapeType": 0, "Procession": 0, "Lines": {"WritingDirection": 0, "Children": []},
             "Cookie": {"Photoshop": {"ShapeType": 0, "PointBase": [float(x), float(y)],
                                      "Base": {"ShapeType": 0, "TransformPoint0": [1.0, 0.0],
                                               "TransformPoint1": [0.0, 1.0],
                                               "TransformPoint2": [0.0, 0.0]}}}}]}},
    }
    return engine_bytes({"EngineDict": engine, "ResourceDict": resources, "DocumentResources": resources})


# --- the layer ------------------------------------------------------------------------------

def _enum(type_id, value):
    return Enumerated(typeID=type_id, enum=value)


def _rect(left, top, right, bottom):
    d = Descriptor(classID=b"Rctn")
    for key, v in ((b"Left", left), (b"Top ", top), (b"Rght", right), (b"Btom", bottom)):
        d[key] = UnitFloat(unit=Unit.Pixels, value=float(v))
    return d


def type_setting(paragraphs, fonts, colour, x, y, box):
    """The TypeToolObjectSetting block. (x, y): where the first baseline starts; box: the
    (left, top, right, bottom) of the ink."""
    text = Descriptor(classID=b"TxLr")
    text[b"Txt "] = String("\r".join("".join(r[0] for r in line) for line in paragraphs) + "\r")
    text[b"textGridding"] = _enum(b"textGridding", b"None")
    text[b"Ornt"] = _enum(b"Ornt", b"Hrzn")
    text[b"AntA"] = _enum(b"Annt", b"AnSm")
    text[b"bounds"] = _rect(*box)
    text[b"boundingBox"] = _rect(*box)
    text[b"TextIndex"] = Integer(0)
    text[b"EngineData"] = RawData(engine_data(paragraphs, fonts, colour, x, y))
    warp = Descriptor(classID=b"warp")
    warp[b"warpStyle"] = _enum(b"warpStyle", b"warpNone")
    warp[b"warpValue"] = Double(0.0)
    warp[b"warpPerspective"] = Double(0.0)
    warp[b"warpPerspectiveOther"] = Double(0.0)
    warp[b"warpRotate"] = _enum(b"Ornt", b"Hrzn")
    block = DescriptorBlock(name="", classID=text.classID)
    block.update(text)
    warp_block = DescriptorBlock(name="", classID=warp.classID)
    warp_block.update(warp)
    return TypeToolObjectSetting(transform=(1.0, 0.0, 0.0, 1.0, float(x), float(y)), text_version=50,
                                 text_data=block,
                                 warp=warp_block, left=int(box[0]), top=int(box[1]),
                                 right=int(box[2]), bottom=int(box[3]))


def add_text_layer(parent, image, name, left, top, paragraphs, fonts, colour, x, y):
    """A pixel layer (`image`, RGBA, placed at left/top) that is also a text layer: paragraphs
    is [[(text, font, size, faux bold, leading or None), ...], ...], one list per line."""
    record, channels = PixelLayer._build_layer_record_and_channels(
        image.convert("RGBA"), name, left, top, Compression.RLE)
    box = (left, top, left + image.width, top + image.height)
    record.tagged_blocks[Tag.TYPE_TOOL_OBJECT_SETTING] = TaggedBlock(
        key=Tag.TYPE_TOOL_OBJECT_SETTING, data=type_setting(paragraphs, fonts, colour, x, y, box))
    layer = PixelLayer(parent, record, channels)
    parent.append(layer)
    return layer
