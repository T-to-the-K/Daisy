import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from PIL import Image


def _image_exts():
    exts = set()
    for ext, fmt in Image.registered_extensions().items():
        if fmt not in Image.SAVE or fmt not in Image.OPEN or fmt == "PDF":
            continue
        try:
            probe = io.BytesIO()
            Image.new("RGB", (2, 2)).save(probe, format=fmt)
        except Exception:
            continue
        exts.add(ext)
    return exts


IMAGE_EXTS = _image_exts()
LOSSY_FMTS = {"JPEG", "MPO", "JFIF", "WEBP"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".opus", ".aac", ".aiff"}
WRITER_EXTS = {".txt", ".md", ".docx", ".odt", ".rtf", ".doc"}
CALC_EXTS = {".csv", ".xls", ".xlsx"}
IMPRESS_EXTS = {".ppt", ".pptx"}

OPS = []


def op(label, kind, applies, run, leveled=False):
    OPS.append(
        {
            "label": label,
            "kind": kind,
            "applies": applies,
            "run": run,
            "leveled": leveled,
        }
    )


def _level(level):
    if level is None:
        return 0.5
    return max(0.0, min(1.0, float(level)))


def output_path(src, ext):
    base = os.path.splitext(src)[0]
    candidate = base + ext
    counter = 2
    while os.path.exists(candidate):
        candidate = "%s (%d)%s" % (base, counter, ext)
        counter += 1
    return candidate


def exts_of(paths):
    return [os.path.splitext(p)[1].lower() for p in paths]


def all_in(paths, allowed):
    return len(paths) > 0 and all(e in allowed for e in exts_of(paths))


def _convert_image(target):
    def run(paths):
        made = []
        for src in paths:
            dst = output_path(src, "." + target)
            im = Image.open(src)
            if target == "jpg":
                im.convert("RGB").save(dst, "JPEG", quality=92)
            elif target == "png":
                im.save(dst, "PNG")
            elif target == "webp":
                im.save(dst, "WEBP", quality=90)
            elif target == "tiff":
                im.save(dst, "TIFF")
            elif target == "bmp":
                im.convert("RGB").save(dst, "BMP")
            elif target == "gif":
                im.convert("RGB").save(dst, "GIF")
            made.append(dst)
        return made

    return run


def _gst_audio(target):
    encoders = {
        "mp3": ["lamemp3enc"],
        "ogg": ["vorbisenc", "oggmux"],
        "flac": ["flacenc"],
        "m4a": ["avenc_aac", "mp4mux"],
        "wav": ["wavenc"],
    }
    stages = []
    for element in encoders[target]:
        stages.append(element)
        stages.append("!")

    def run(paths):
        made = []
        for src in paths:
            dst = output_path(src, "." + target)
            args = (
                ["gst-launch-1.0", "-q", "filesrc", "location=" + src, "!"]
                + ["decodebin", "!"]
                + ["audioconvert", "!"]
                + ["audioresample", "!"]
                + stages
                + ["filesink", "location=" + dst]
            )
            subprocess.run(args, check=True, capture_output=True, timeout=120)
            made.append(dst)
        return made

    return run


def _libreoffice(target):
    def run(paths):
        made = []
        for src in paths:
            src_ext = os.path.splitext(src)[1].lower()
            if src_ext == "." + target:
                raise RuntimeError("%s is already a %s file" % (os.path.basename(src), target.upper()))
            dst = output_path(src, "." + target)
            base = os.path.splitext(os.path.basename(src))[0]
            workdir = tempfile.mkdtemp(prefix="daisy-lo-")
            try:
                command = ["libreoffice", "--headless"]
                if src_ext == ".pdf":
                    command.append("--infilter=writer_pdf_import")
                command += [
                    "--convert-to",
                    target,
                    "--outdir",
                    workdir,
                    os.path.abspath(src),
                ]
                subprocess.run(command, check=True, capture_output=True, timeout=180)
                produced = os.path.join(workdir, base + "." + target)
                if not os.path.exists(produced) or os.path.getsize(produced) == 0:
                    raise RuntimeError(
                        "LibreOffice could not create a %s copy of %s"
                        % (target.upper(), os.path.basename(src))
                    )
                shutil.move(produced, dst)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            made.append(dst)
        return made

    return run


def images_to_pdf(paths):
    dst = output_path(paths[0], ".pdf")
    pages = [Image.open(p).convert("RGB") for p in paths]
    pages[0].save(dst, "PDF", save_all=True, append_images=pages[1:])
    return [dst]


def pdf_to_pages(paths, fmt):
    made = []
    for src in paths:
        stem = os.path.join(
            os.path.dirname(src) or ".",
            os.path.splitext(os.path.basename(src))[0] + "-page",
        )
        tmpdir = tempfile.mkdtemp(prefix="daisy-pdf-")
        try:
            args = [
                "pdftoppm",
                "-" + ("png" if fmt == "png" else "jpeg"),
                "-r",
                "150",
                src,
                os.path.join(tmpdir, "page"),
            ]
            subprocess.run(args, check=True, capture_output=True, timeout=120)
            pages = [
                p
                for p in os.listdir(tmpdir)
                if re.match(r"page-\d+\.(png|jpe?g)$", p, re.IGNORECASE)
            ]
            if not pages:
                raise RuntimeError("Could not render any pages of %s" % os.path.basename(src))
            pages.sort(key=lambda p: int(re.search(r"-(\d+)\.", p).group(1)))
            for page in pages:
                index = int(re.search(r"-(\d+)\.", page).group(1))
                dst = "%s-%d.%s" % (stem, index, fmt)
                counter = 2
                while os.path.exists(dst):
                    dst = "%s-%d-%d.%s" % (stem, index, counter, fmt)
                    counter += 1
                shutil.move(os.path.join(tmpdir, page), dst)
                made.append(dst)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return made


def pdf_to_text(paths):
    made = []
    for src in paths:
        dst = output_path(src, ".txt")
        subprocess.run(["pdftotext", src, dst], check=True, capture_output=True, timeout=60)
        made.append(dst)
    return made


def _fmt_of(path):
    return Image.registered_extensions().get(os.path.splitext(path)[1].lower())


def _save(im, dst, fmt, **params):
    if fmt == "ICO":
        params.setdefault("sizes", [im.size])
    try:
        im.save(dst, format=fmt, **params)
    except (TypeError, ValueError, OSError):
        fallback = {"sizes": params["sizes"]} if "sizes" in params else {}
        im.save(dst, format=fmt, **fallback)


def _load(path):
    opened = Image.open(path)
    opened.load()
    return opened.copy(), opened


def compress_image(paths, level=None):
    level = _level(level)
    made = []
    for src in paths:
        ext = os.path.splitext(src)[1].lower()
        dst = output_path(src, "-compressed" + ext)
        original = os.path.getsize(src)
        fmt = _fmt_of(src)
        im, opened = _load(src)
        opened.close()
        if fmt in LOSSY_FMTS:
            quality = int(round(92 - 64 * level))
            ratio = 0.90 - 0.55 * level
            _save(im, dst, fmt, quality=quality, optimize=True)
            while os.path.getsize(dst) > original * ratio and quality > 25:
                quality -= 5
                _save(im, dst, fmt, quality=quality, optimize=True)
        elif fmt in ("PNG", "APNG"):
            _save(im, dst, fmt, optimize=True)
            if level >= 0.5 or os.path.getsize(dst) >= original:
                try:
                    colors = max(32, int(round(256 - 200 * level)))
                    if im.mode in ("RGBA", "LA", "P"):
                        work = im.convert("RGBA")
                        pal = work.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
                    else:
                        pal = im.convert("RGB").quantize(colors=colors)
                    _save(pal, dst, fmt, optimize=True)
                except Exception:
                    pass
        elif fmt == "TIFF":
            _save(im, dst, fmt, compression="tiff_lzw")
        else:
            _save(im, dst, fmt, optimize=True)
        made.append(dst)
    return made


def resize_image(paths):
    made = []
    for src in paths:
        ext = os.path.splitext(src)[1].lower()
        dst = output_path(src, "-small" + ext)
        fmt = _fmt_of(src)
        im, opened = _load(src)
        opened.close()
        small = im.resize(
            (max(1, im.width // 2), max(1, im.height // 2)), Image.LANCZOS
        )
        _save(small, dst, fmt)
        made.append(dst)
    return made


def rotate_image(paths):
    made = []
    for src in paths:
        ext = os.path.splitext(src)[1].lower()
        dst = output_path(src, "-rotated" + ext)
        fmt = _fmt_of(src)
        im, opened = _load(src)
        opened.close()
        _save(im.rotate(90, expand=True), dst, fmt)
        made.append(dst)
    return made


def strip_meta(paths):
    made = []
    for src in paths:
        ext = os.path.splitext(src)[1].lower()
        dst = output_path(src, "-clean" + ext)
        fmt = _fmt_of(src)
        im, opened = _load(src)
        keep = {
            key: value
            for key, value in opened.info.items()
            if key in ("transparency", "duration", "loop", "background", "disposal")
        }
        opened.close()
        clean = Image.new(im.mode, im.size)
        if im.mode == "P":
            clean.putpalette(im.getpalette())
        clean.paste(im)
        clean.info = keep
        if fmt in LOSSY_FMTS:
            _save(clean, dst, fmt, quality=95)
        elif fmt in ("PNG", "APNG"):
            _save(clean, dst, fmt, optimize=True)
        else:
            _save(clean, dst, fmt)
        made.append(dst)
    return made


def make_archive(paths, kind):
    first = os.path.splitext(os.path.basename(paths[0]))[0]
    if len(paths) == 1:
        name = first
    else:
        name = first + "-files"
    ext = ".zip" if kind == "zip" else ".tar.gz"
    folder = os.path.dirname(paths[0]) or "."
    base = os.path.join(folder, name)
    candidate = base + ext
    counter = 2
    while os.path.exists(candidate):
        candidate = "%s-%d%s" % (base, counter, ext)
        counter += 1

    used = set()

    def arcname(path):
        name = os.path.basename(path)
        stem, suffix = os.path.splitext(name)
        candidate_name = name
        n = 2
        while candidate_name in used:
            candidate_name = "%s (%d)%s" % (stem, n, suffix)
            n += 1
        used.add(candidate_name)
        return candidate_name

    if kind == "zip":
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, arcname(path))
    else:
        with tarfile.open(candidate, "w:gz") as archive:
            for path in paths:
                archive.add(path, arcname=arcname(path))
    return [candidate]


def clipboard(text):
    subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)


def copy_path(paths):
    clipboard("\n".join(paths))
    return []


def duplicate_file(paths):
    made = []
    for src in paths:
        name = os.path.basename(src)
        folder = os.path.dirname(src) or "."
        dst = os.path.join(folder, "copy of " + name)
        counter = 2
        while os.path.exists(dst):
            dst = os.path.join(folder, "copy (%d) of %s" % (counter, name))
            counter += 1
        shutil.copy2(src, dst)
        made.append(dst)
    return made


def open_file(paths):
    for src in paths:
        subprocess.Popen(["xdg-open", src], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return []


def open_terminal(paths):
    folder = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")
    subprocess.Popen(["x-terminal-emulator", "--working-directory", folder])
    return []


def reveal_file(paths):
    folder = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")
    subprocess.Popen(["xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return []


def _pdf_preset(level):
    level = _level(level)
    if level < 0.2:
        return "/prepress"
    if level < 0.45:
        return "/printer"
    if level < 0.75:
        return "/ebook"
    return "/screen"


def compress_pdf(paths, level=None):
    made = []
    for src in paths:
        dst = output_path(src, "-compressed.pdf")
        # Try ghostscript for compression
        subprocess.run(
            [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=" + _pdf_preset(level),
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                "-sOutputFile=" + dst,
                src,
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        made.append(dst)
    return made


def compress_office(paths, level=None):
    made = []
    # For office formats, convert to PDF then compress
    for src in paths:
        tmpdir = tempfile.mkdtemp(prefix="daisy-office-")
        try:
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmpdir,
                    os.path.abspath(src),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            pdf_path = os.path.join(
                tmpdir, os.path.splitext(os.path.basename(src))[0] + ".pdf"
            )
            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
                raise RuntimeError(
                    "LibreOffice could not create a PDF copy of %s"
                    % os.path.basename(src)
                )
            dst = output_path(src, "-compressed.pdf")
            subprocess.run(
                [
                    "gs",
                    "-sDEVICE=pdfwrite",
                    "-dCompatibilityLevel=1.4",
                    "-dPDFSETTINGS=" + _pdf_preset(level),
                    "-dNOPAUSE",
                    "-dQUIET",
                    "-dBATCH",
                    "-sOutputFile=" + dst,
                    pdf_path,
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        made.append(dst)
    return made


def build():
    OPS.clear()
    for target in ("png", "jpg", "webp", "tiff", "bmp", "gif"):
        op(target.upper(), "convert", lambda p, t=target: all_in(p, IMAGE_EXTS), _convert_image(target))
    op("PDF", "convert", lambda p: all_in(p, IMAGE_EXTS), images_to_pdf)
    op("PNG", "convert", lambda p: all_in(p, {".pdf"}), lambda p: pdf_to_pages(p, "png"))
    op("JPG", "convert", lambda p: all_in(p, {".pdf"}), lambda p: pdf_to_pages(p, "jpg"))
    op("TXT", "convert", lambda p: all_in(p, {".pdf"}), pdf_to_text)
    for target in ("mp3", "ogg", "flac", "m4a", "wav"):
        op(target.upper(), "convert", lambda p, t=target: all_in(p, AUDIO_EXTS), _gst_audio(target))
    for target in ("pdf", "docx", "doc", "txt", "odt", "rtf"):
        op(
            target.upper(),
            "convert",
            lambda p, t=target: all_in(p, WRITER_EXTS | {".pdf"}),
            _libreoffice(target),
        )
    for target in ("pdf", "xls", "xlsx", "csv"):
        op(
            target.upper(),
            "convert",
            lambda p, t=target: all_in(p, CALC_EXTS),
            _libreoffice(target),
        )
    for target in ("pdf", "ppt", "pptx"):
        op(
            target.upper(),
            "convert",
            lambda p, t=target: all_in(p, IMPRESS_EXTS),
            _libreoffice(target),
        )
    op("ZIP", "convert", lambda p: len(p) > 0, lambda p: make_archive(p, "zip"))
    op("TGZ", "convert", lambda p: len(p) > 0, lambda p: make_archive(p, "tgz"))
    # Image tools for all images
    op("Compress", "tool", lambda p: all_in(p, IMAGE_EXTS), compress_image, leveled=True)
    op("Resize", "tool", lambda p: all_in(p, IMAGE_EXTS), resize_image)
    op("Rotate", "tool", lambda p: all_in(p, IMAGE_EXTS), rotate_image)
    op("Strip", "tool", lambda p: all_in(p, IMAGE_EXTS), strip_meta)
    # PDF/Office compression
    op("Compress", "tool", lambda p: all_in(p, {".pdf"}), compress_pdf, leveled=True)
    op(
        "Compress",
        "tool",
        lambda p: all_in(p, {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt"}),
        compress_office,
        leveled=True,
    )
    op("Path", "action", lambda p: True, copy_path)
    op("Copy", "action", lambda p: True, duplicate_file)
    op("Open", "action", lambda p: True, open_file)
    op("Term", "action", lambda p: True, open_terminal)
    op("Reveal", "action", lambda p: True, reveal_file)
    return OPS


def ops_for(kind, paths=None):
    found = [o for o in OPS if o["kind"] == kind]
    if paths:
        applicable = [
            o
            for o in found
            if any(o["applies"]([path]) for path in paths)
        ]
        if applicable:
            found = applicable
        if kind == "convert":
            exts = set(exts_of(paths))
            found = [
                o
                for o in found
                if ("." + o["label"].lower()) not in exts
                or o["label"] in ("ZIP", "TGZ")
            ]
    seen = set()
    unique = []
    for entry in found:
        if entry["label"] in seen:
            continue
        seen.add(entry["label"])
        item = dict(entry)
        item["enabled"] = bool(paths) and entry["applies"](paths)
        unique.append(item)
    return unique


def run_op(entry, paths, level=None):
    matches = [o for o in OPS if o["label"] == entry["label"] and o["kind"] == entry["kind"]]
    for match in matches:
        if match["applies"](paths):
            if match.get("leveled"):
                return match["run"](paths, level)
            return match["run"](paths)
    raise ValueError("%s does not work on these files" % entry["label"])
