import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from PIL import Image, PngImagePlugin

import ops


def find_op(label, kind):
    return next(o for o in ops.OPS if o["label"] == label and o["kind"] == kind)


class TestOpsEdgeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ops.build()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def make_gif(self, size=(8, 4), frames=3):
        src = self.path("anim.gif")
        images = [Image.new("RGB", size, (i * 80, 10, 10)) for i in range(frames)]
        images[0].save(
            src, save_all=True, append_images=images[1:], duration=100, loop=0
        )
        return src

    def test_same_format_aliases_are_not_offered(self):
        cases = {
            "a.jpeg": "JPG",
            "a.JPE": "JPG",
            "a.jfif": "JPG",
            "a.tif": "TIFF",
            "a.TIFF": "TIFF",
            "a.dib": "BMP",
            "a.apng": "PNG",
        }
        for name, excluded in cases.items():
            labels = [o["label"] for o in ops.ops_for("convert", [name])]
            self.assertNotIn(excluded, labels, name)
            self.assertIn("ZIP", labels, name)

    def test_source_format_still_not_offered_for_exact_ext(self):
        labels = [o["label"] for o in ops.ops_for("convert", ["a.png"])]
        self.assertNotIn("PNG", labels)
        self.assertIn("JPG", labels)

    def test_archive_directory_with_trailing_separator(self):
        folder = self.path("folder")
        os.makedirs(os.path.join(folder, "sub"))
        with open(os.path.join(folder, "a.txt"), "w") as handle:
            handle.write("hi")
        with open(os.path.join(folder, "sub", "b.txt"), "w") as handle:
            handle.write("yo")

        made = ops.make_archive([folder + os.sep], "zip")

        self.assertEqual(made, [self.path("folder.zip")])
        with zipfile.ZipFile(made[0]) as archive:
            self.assertEqual(
                sorted(archive.namelist()), ["folder/a.txt", "folder/sub/b.txt"]
            )

    def test_archive_folder_contents_are_nested_under_folder_name(self):
        folder = self.path("photos")
        os.makedirs(folder)
        with open(os.path.join(folder, "one.txt"), "w") as handle:
            handle.write("1")

        made = ops.make_archive([folder], "tgz")

        with tarfile.open(made[0]) as archive:
            names = archive.getnames()
        self.assertIn("photos/one.txt", names)

    def test_archive_deduplicates_same_basenames(self):
        first = self.path("one")
        second = self.path("two")
        os.makedirs(first)
        os.makedirs(second)
        for folder in (first, second):
            with open(os.path.join(folder, "a.txt"), "w") as handle:
                handle.write(folder)

        made = ops.make_archive(
            [os.path.join(first, "a.txt"), os.path.join(second, "a.txt")], "zip"
        )

        with zipfile.ZipFile(made[0]) as archive:
            self.assertEqual(sorted(archive.namelist()), ["a (2).txt", "a.txt"])

    def test_duplicate_directory(self):
        folder = self.path("folder")
        os.makedirs(os.path.join(folder, "sub"))
        with open(os.path.join(folder, "sub", "a.txt"), "w") as handle:
            handle.write("kept")

        made = ops.duplicate_file([folder])

        self.assertEqual(made, [self.path("copy of folder")])
        with open(os.path.join(made[0], "sub", "a.txt")) as handle:
            self.assertEqual(handle.read(), "kept")

    def test_duplicate_directory_with_trailing_separator(self):
        folder = self.path("folder")
        os.makedirs(folder)
        with open(os.path.join(folder, "a.txt"), "w") as handle:
            handle.write("kept")

        made = ops.duplicate_file([folder + os.sep])

        self.assertEqual(made, [self.path("copy of folder")])

    def test_terminal_and_reveal_open_a_dragged_directory(self):
        folder = self.path("folder")
        os.makedirs(folder)

        with mock.patch("ops.subprocess.Popen") as popen:
            ops.open_terminal([folder])
            popen.assert_called_once_with(
                ["x-terminal-emulator", "--working-directory", folder]
            )

        with mock.patch("ops.subprocess.Popen") as popen:
            ops.reveal_file([folder])
            popen.assert_called_once_with(
                ["xdg-open", folder],
                stdout=ops.subprocess.DEVNULL,
                stderr=ops.subprocess.DEVNULL,
            )

    def test_duplicate_file_avoids_existing_copy(self):
        src = self.path("note.txt")
        with open(src, "w") as handle:
            handle.write("hi")

        first = ops.duplicate_file([src])[0]
        second = ops.duplicate_file([src])[0]

        self.assertEqual(first, self.path("copy of note.txt"))
        self.assertEqual(second, self.path("copy (2) of note.txt"))

    def test_strip_meta_removes_png_text_metadata(self):
        src = self.path("tagged.png")
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", "private note")
        Image.new("RGB", (4, 4), (10, 20, 30)).save(src, pnginfo=info)

        made = ops.strip_meta([src])[0]

        with Image.open(made) as stripped:
            self.assertNotIn("Comment", stripped.info)

    def test_image_tools_preserve_animation(self):
        src = self.make_gif()

        resized = ops.resize_image([src])[0]
        rotated = ops.rotate_image([src])[0]
        cleaned = ops.strip_meta([src])[0]
        compressed = ops.compress_image([src])[0]

        with Image.open(resized) as im:
            self.assertEqual(im.n_frames, 3)
            self.assertEqual(im.size, (4, 2))
        with Image.open(rotated) as im:
            self.assertEqual(im.n_frames, 3)
            self.assertEqual(im.size, (4, 8))
        with Image.open(cleaned) as im:
            self.assertEqual(im.n_frames, 3)
        with Image.open(compressed) as im:
            self.assertEqual(im.n_frames, 3)

    def test_compress_reduces_a_lossy_image(self):
        src = self.path("noise.jpg")
        pixels = [
            ((x * 37) % 256, (x * 91) % 256, (x * 13) % 256)
            for x in range(96 * 96)
        ]
        noise = Image.new("RGB", (96, 96))
        noise.putdata(pixels)
        noise.save(src, quality=100)

        made = ops.compress_image([src], 1.0)[0]

        with Image.open(made) as compressed:
            self.assertEqual(compressed.size, (96, 96))
            self.assertEqual(compressed.mode, "RGB")
        self.assertLess(os.path.getsize(made), os.path.getsize(src))

    def test_convert_png_to_jpg(self):
        src = self.path("image.png")
        Image.new("RGBA", (5, 5), (1, 2, 3, 255)).save(src)

        made = ops.run_op(find_op("JPG", "convert"), [src])

        self.assertEqual(made, [self.path("image.jpg")])
        with Image.open(made[0]) as converted:
            self.assertEqual(converted.format, "JPEG")
            self.assertEqual(converted.mode, "RGB")
            self.assertEqual(converted.size, (5, 5))

    def test_convert_preserves_gif_animation(self):
        src = self.make_gif()

        for label in ("PNG", "WEBP", "TIFF"):
            made = ops.run_op(find_op(label, "convert"), [src])
            with Image.open(made[0]) as converted:
                self.assertEqual(converted.n_frames, 3, label)
                self.assertEqual(converted.size, (8, 4), label)

    def test_convert_images_to_pdf(self):
        first = self.path("one.png")
        second = self.path("two.png")
        Image.new("RGB", (5, 5), (255, 0, 0)).save(first)
        Image.new("RGB", (5, 5), (0, 0, 255)).save(second)

        made = ops.run_op(find_op("PDF", "convert"), [first, second])

        self.assertEqual(made, [self.path("one.pdf")])
        with open(made[0], "rb") as handle:
            self.assertTrue(handle.read(5).startswith(b"%PDF"))

    def test_tool_does_not_run_on_wrong_kind(self):
        src = self.path("notes.txt")
        with open(src, "w") as handle:
            handle.write("hello")
        with self.assertRaises(ValueError):
            ops.run_op(find_op("Resize", "tool"), [src])


if __name__ == "__main__":
    unittest.main()
