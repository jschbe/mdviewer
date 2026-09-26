import tempfile
import unittest
from pathlib import Path

from mdview.render import local_image, read_document, render


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_common_markdown(self):
        source = '# Heading\n\n- item\n\n> quote\n\n`inline`\n\n---\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n~~gone~~'
        page = render(source, self.root).html
        for tag in ('<h1 id="heading">', '<ul>', '<blockquote>', '<code>inline</code>', '<hr', '<table>', '<s>gone</s>'):
            self.assertIn(tag, page)

    def test_code_payload_and_highlighting(self):
        result = render('```python\nprint("héllo <&>")\n\n```\n\n```unknown-language\nx\n```\n\n```\ny\n```', self.root)
        self.assertEqual(result.codes, ['print("héllo <&>")\n\n', 'x\n', 'y\n'])
        self.assertEqual(result.html.count('aria-label="Copy code"'), 3)
        self.assertIn('<span class=', result.html)
        self.assertNotIn('class="linenos"', result.html)

    def test_untrusted_markup(self):
        result = render('<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[x](javascript:alert%281%29)\n\n```\n</code><script>bad()</script>\n```', self.root)
        self.assertEqual(result.html.count('<script>'), 1)
        self.assertNotIn('<img src=x', result.html)
        self.assertNotIn('href="javascript:', result.html)
        self.assertIn("default-src &#x27;none&#x27;", result.html)
        self.assertIn('script-src &#x27;sha256-', result.html)

    def test_images_and_boundaries(self):
        image = self.root / 'a b.png'
        image.write_bytes(b'fake image')
        self.assertTrue(local_image('a%20b.png', self.root).startswith('data:image/png;base64,'))
        for src in ('https://example.com/x.png', '//example.com/x.png', '../x.png', 'data:image/png;base64,eA==', 'file:///tmp/x.png', 'x.svg'):
            self.assertIsNone(local_image(src, self.root))
        (self.root / 'escape.png').symlink_to('/etc/passwd')
        self.assertIsNone(local_image('escape.png', self.root))
        self.assertIn('Image unavailable', render('![remote](https://example.com/x.png)', self.root).html)

    def test_utf8_and_invalid_files(self):
        path = self.root / 'test.md'
        path.write_bytes(b'\xef\xbb\xbf' + 'Grüße 日本語'.encode())
        self.assertEqual(read_document(path), 'Grüße 日本語')
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeError):
            read_document(path)
        with self.assertRaises(ValueError):
            read_document(self.root)

    def test_heading_ids_and_local_links(self):
        page = render('# Hello\n\n# Hello\n\n[other](other%20file.md)\n\n[jump](#hello)', self.root).html
        self.assertIn('id="hello-1"', page)
        self.assertIn((self.root / 'other file.md').as_uri(), page)
        self.assertIn('href="#hello"', page)


if __name__ == '__main__':
    unittest.main()
