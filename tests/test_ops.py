import os
import tempfile
import unittest

import ops


class TestOps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ops.build()

    def test_level_clamp(self):
        self.assertEqual(ops._level(None), 0.5)
        self.assertEqual(ops._level(0.0), 0.0)
        self.assertEqual(ops._level(1.0), 1.0)
        self.assertEqual(ops._level(5), 1.0)
        self.assertEqual(ops._level(-3), 0.0)

    def test_exts_of(self):
        self.assertEqual(ops.exts_of(["a.PDF", "b.png"]), [".pdf", ".png"])

    def test_all_in(self):
        self.assertTrue(ops.all_in(["a.png", "b.jpg"], ops.IMAGE_EXTS))
        self.assertFalse(ops.all_in(["a.png", "b.txt"], ops.IMAGE_EXTS))
        self.assertFalse(ops.all_in([], ops.IMAGE_EXTS))

    def test_output_path_unique(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "report")
            p1 = ops.output_path(base + ".pdf", ".txt")
            self.assertEqual(p1, base + ".txt")
            open(p1, "w").close()
            p2 = ops.output_path(base + ".pdf", ".txt")
            self.assertEqual(p2, base + " (2).txt")

    def test_build_registers_ops(self):
        self.assertGreater(len(ops.OPS), 0)
        for entry in ops.OPS:
            self.assertIn("label", entry)
            self.assertIn("kind", entry)
            self.assertIn("applies", entry)
            self.assertIn("run", entry)

    def test_ops_for_convert_pdf(self):
        found = ops.ops_for("convert", ["report.pdf"])
        labels = [o["label"] for o in found]
        self.assertIn("PNG", labels)
        self.assertIn("TXT", labels)
        # the source format should not be offered as a target
        self.assertNotIn("PDF", labels)

    def test_ops_for_returns_entries(self):
        found = ops.ops_for("convert", ["photo.png"])
        self.assertTrue(all(isinstance(o, dict) for o in found))

    def test_run_op_rejects_wrong_kind(self):
        with self.assertRaises(ValueError):
            # Resize does not apply to a text file
            ops.run_op({"label": "Resize", "kind": "tool"}, ["notes.txt"])


if __name__ == "__main__":
    unittest.main()
