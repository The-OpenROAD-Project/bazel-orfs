"""md_to_pdf on what README.md is made of: headings, a table with code in
its cells, a code block, micro signs and an SVG; the PDF has pages and
the same inputs make the same bytes."""

import os
import tempfile
import unittest

import md_to_pdf

HERE = os.path.dirname(os.path.abspath(__file__))

MD = """# Title

Text with `code`, **bold** and *italics*, 4,771 x 2,064 µm.

| Macro | W x H um |
|---|---:|
| `array_64x64` | 10.0 x 5.0 |

```
set clk_period 2000
```

![a diagram](clock_boundary.svg)
"""


class PdfTest(unittest.TestCase):
    def test_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, "README.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write(MD)
            outs = []
            for name in ("a.pdf", "b.pdf"):
                out = os.path.join(d, name)
                md_to_pdf.main(
                    [
                        "--out",
                        out,
                        "--image",
                        "clock_boundary.svg="
                        + os.path.join(HERE, "clock_boundary.svg"),
                        md,
                    ]
                )
                outs.append(open(out, "rb").read())
            self.assertTrue(outs[0].startswith(b"%PDF"))
            self.assertIn(b"/Type /Page", outs[0])
            self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
