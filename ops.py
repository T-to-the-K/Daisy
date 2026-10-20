import os
import shutil
import subprocess

from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".opus", ".aac", ".aiff"}
TEXT_EXTS = {".txt", ".md", ".docx", ".odt", ".rtf", ".csv"}

OPS = []


def op(label, kind, applies, run):
    OPS.append({"label": label, "kind": kind, "applies": applies, "run": run})


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
            dst = output_path(src, "." + target)
            workdir = os.path.dirname(dst)
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    target,
                    "--outdir",
                    workdir,
                    src,
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            produced = os.path.join(
                workdir, os.path.splitext(os.path.basename(src))[0] + "." + target
            )
            if produced != dst and os.path.exists(produced):
                os.replace(produced, dst)
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
        prefix = output_path(src, "").rstrip(".") + "-page"
        args = ["pdftoppm", "-" + ("png" if fmt == "png" else "jpeg"), "-r", "150", src, prefix]
        subprocess.run(args, check=True, capture_output=True, timeout=120)
        pages = sorted(
            p for p in os.listdir(os.path.dirname(src) or ".") if p.startswith(os.path.basename(prefix))
        )
        for page in pages:
            full = os.path.join(os.path.dirname(src) or ".", page)
            dst = full if page.endswith("." + fmt) else full + "." + fmt
            if full != dst:
                os.replace(full, dst)
            made.append(dst)
    return made


def pdf_to_text(paths):
    made = []
    for src in paths:
        dst = output_path(src, ".txt")
        subprocess.run(["pdftotext", src, dst], check=True, capture_output=True, timeout=60)
        made.append(dst)
    return made


def compress_image(paths):
    made = []
    for src in paths:
        dst = output_path(src, "-compressed" + os.path.splitext(src)[1])
        original = os.path.getsize(src)
        im = Image.open(src)
        quality = 75
        im.save(dst, quality=quality)
        while os.path.getsize(dst) > original * 0.6 and quality > 30:
            quality -= 10
            im.save(dst, quality=quality)
        made.append(dst)
    return made


def resize_image(paths):
    made = []
    for src in paths:
        dst = output_path(src, "-small" + os.path.splitext(src)[1])
        im = Image.open(src)
        im.resize((im.width // 2, im.height // 2)).save(dst)
        made.append(dst)
    return made


def rotate_image(paths):
    made = []
    for src in paths:
        dst = output_path(src, "-rotated" + os.path.splitext(src)[1])
        Image.open(src).rotate(90, expand=True).save(dst)
        made.append(dst)
    return made


def strip_meta(paths):
    made = []
    for src in paths:
        dst = output_path(src, "-clean" + os.path.splitext(src)[1])
        im = Image.open(src)
        clean = Image.new(im.mode, im.size)
        clean.putdata(list(im.getdata()))
        clean.save(dst)
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
    if kind == "zip":
        subprocess.run(["zip", "-j", candidate] + paths, check=True, capture_output=True, timeout=300)
    else:
        subprocess.run(
            ["tar", "-czf", candidate, "-C", folder]
            + [os.path.basename(p) for p in paths],
            check=True,
            capture_output=True,
            timeout=300,
        )
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
    for target in ("pdf", "docx", "txt"):
        op(
            target.upper(),
            "convert",
            lambda p, t=target: all_in(p, TEXT_EXTS),
            _libreoffice(target),
        )
    op("ZIP", "convert", lambda p: len(p) > 0, lambda p: make_archive(p, "zip"))
    op("TGZ", "convert", lambda p: len(p) > 0, lambda p: make_archive(p, "tgz"))
    op("Compress", "tool", lambda p: all_in(p, IMAGE_EXTS), compress_image)
    op("Resize", "tool", lambda p: all_in(p, IMAGE_EXTS), resize_image)
    op("Rotate", "tool", lambda p: all_in(p, IMAGE_EXTS), rotate_image)
    op("Strip meta", "tool", lambda p: all_in(p, IMAGE_EXTS), strip_meta)
    op("Path", "action", lambda p: True, copy_path)
    op("Copy", "action", lambda p: True, duplicate_file)
    op("Open", "action", lambda p: True, open_file)
    op("Term", "action", lambda p: True, open_terminal)
    op("Reveal", "action", lambda p: True, reveal_file)
    return OPS


def ops_for(kind, paths=None):
    found = [o for o in OPS if o["kind"] == kind]
    if paths:
        found = [o for o in found if o["applies"](paths)]
        if kind == "convert":
            exts = set(exts_of(paths))
            found = [
                o
                for o in found
                if ("." + o["label"].lower()) not in exts
                or o["label"] in ("PDF", "ZIP", "TGZ")
            ]
    seen = set()
    unique = []
    for entry in found:
        if entry["label"] in seen:
            continue
        seen.add(entry["label"])
        unique.append(entry)
    return unique


def run_op(entry, paths):
    matches = [o for o in OPS if o["label"] == entry["label"] and o["kind"] == entry["kind"]]
    for match in matches:
        if match["applies"](paths):
            return match["run"](paths)
    raise ValueError("%s does not work on these files" % entry["label"])
