import archive
from archive import (
    append_section,
    archive as run_archive,
    build_highlights_note,
    extract_url,
    new_highlights,
    normalize_url,
    render_highlights,
    vault_filename,
)


class TestNormalizeUrl:
    def test_strips_utm_and_tracking(self):
        assert normalize_url("https://ex.com/a?utm_source=x&id=5&fbclid=z") == \
            "https://ex.com/a?id=5"

    def test_strips_www_fragment_and_trailing_slash(self):
        assert normalize_url("https://www.ex.com/a/#top") == "https://ex.com/a"

    def test_same_article_different_tracking_collapses(self):
        assert normalize_url("https://ex.com/p?utm_medium=a") == \
            normalize_url("https://ex.com/p?utm_medium=b")

    def test_empty(self):
        assert normalize_url("") == ""


class TestVaultFilename:
    def test_removes_illegal_chars(self):
        assert vault_filename("Titolo: con / caratteri? *illegali*") == \
            "Titolo con caratteri illegali"

    def test_empty_fallback(self):
        assert vault_filename("") == "Senza titolo"


class TestExtractUrl:
    def test_finds_url_in_metadata(self):
        note = "## Metadata\n- Author: [[x]]\n- URL: https://ex.com/a\n"
        assert extract_url(note) == "https://ex.com/a"

    def test_none_when_absent(self):
        assert extract_url("nessun url qui") is None


class TestRenderHighlights:
    def test_content_and_note(self):
        out = render_highlights([{"content": "frase", "note": "mio commento"}])
        assert out == "- frase\n    - Note: mio commento"

    def test_prefers_markdown_content_and_skips_empty(self):
        out = render_highlights([
            {"markdownContent": "**bold**", "content": "bold"},
            {"content": "   "},
        ])
        assert out == "- **bold**"


class TestNewHighlights:
    def test_filters_already_present(self):
        existing = "## Highlights\n- gia presente\n"
        hs = [{"content": "gia presente"}, {"content": "nuovo"}]
        assert new_highlights(hs, existing) == [{"content": "nuovo"}]


class TestAppendSection:
    def test_creates_heading_when_absent(self):
        out = append_section("# Nota\ntesto", "## Highlights (GoodLinks)", "- x")
        assert out == "# Nota\ntesto\n\n## Highlights (GoodLinks)\n- x\n"

    def test_appends_under_existing_heading(self):
        base = "# Nota\n\n## Highlights (GoodLinks)\n- vecchio"
        out = append_section(base, "## Highlights (GoodLinks)", "- nuovo")
        assert out == "# Nota\n\n## Highlights (GoodLinks)\n- vecchio\n- nuovo\n"


class TestBuildHighlightsNote:
    def test_contains_metadata_and_highlights(self):
        link = {"title": "Titolo", "url": "https://ex.com/a", "author": "Tizio",
                "summary": "riassunto", "tags": ["publish"]}
        note = build_highlights_note(link, [{"content": "h1"}], "Full/x.md")
        assert "# Titolo" in note
        assert "- URL: https://ex.com/a" in note
        assert "- Author: [[Tizio]]" in note
        assert "- Document Tags: #publish" in note
        assert "[[Full/x.md|See full document content →]]" in note
        assert "- h1" in note


class FakeGoodLinks:
    def __init__(self, links, highlights):
        self._links = links
        self._highlights = highlights

    def get_all_links(self):
        return self._links

    def get_highlights(self, link_id):
        return self._highlights.get(link_id, [])


class FakeObsidian:
    def __init__(self, files=None):
        self.files = dict(files or {})  # path -> content
        self.writes = []

    def list_folder(self, folder):
        prefix = folder + "/"
        return [p[len(prefix):] for p in self.files
                if p.startswith(prefix) and "/" not in p[len(prefix):]]

    def read(self, path):
        return self.files.get(path)

    def write(self, path, content):
        self.files[path] = content
        self.writes.append(path)


def no_fetch(url):
    return "TESTO INTEGRALE"


class TestArchive:
    def test_new_link_creates_both_notes(self):
        gl = FakeGoodLinks(
            [{"id": "1", "title": "Nuovo", "url": "https://ex.com/a", "highlighted": True}],
            {"1": [{"content": "h1"}]})
        obs = FakeObsidian()
        writes = run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch)
        assert writes == 2
        assert "3.Risorse/Articoli/Nuovo.md" in obs.files
        assert "3.Risorse/Full Document Contents/Articoli/Nuovo.md" in obs.files

    def test_link_without_highlighted_flag_skipped(self):
        gl = FakeGoodLinks(
            [{"id": "1", "title": "X", "url": "https://ex.com/a", "highlighted": False}],
            {"1": [{"content": "h1"}]})
        obs = FakeObsidian()
        assert run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch) == 0
        assert obs.writes == []

    def test_existing_url_appends_only_new_highlights(self):
        existing = ("# Vecchio\n\n## Metadata\n- URL: https://ex.com/a\n\n"
                    "## Highlights\n- gia presente\n")
        obs = FakeObsidian({
            "3.Risorse/Articoli/Vecchio.md": existing,
            # full doc esiste già con lo stesso URL -> non ricreato
            "3.Risorse/Full Document Contents/Articoli/Vecchio.md":
                "## Metadata\n- URL: https://ex.com/a\n",
        })
        gl = FakeGoodLinks(
            [{"id": "1", "title": "Vecchio", "url": "https://ex.com/a?utm_x=1",
              "highlighted": True}],
            {"1": [{"content": "gia presente"}, {"content": "nuovo highlight"}]})
        writes = run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch)
        assert writes == 1
        updated = obs.files["3.Risorse/Articoli/Vecchio.md"]
        assert "## Highlights (GoodLinks)" in updated
        assert "- nuovo highlight" in updated
        assert updated.count("- gia presente") == 1

    def test_idempotent_second_run_writes_nothing(self):
        gl = FakeGoodLinks(
            [{"id": "1", "title": "Nuovo", "url": "https://ex.com/a", "highlighted": True}],
            {"1": [{"content": "h1"}]})
        obs = FakeObsidian()
        run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch)
        obs.writes.clear()
        writes = run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch)
        assert writes == 0
        assert obs.writes == []

    def test_fulldoc_skipped_when_extraction_fails(self):
        gl = FakeGoodLinks(
            [{"id": "1", "title": "Nuovo", "url": "https://ex.com/a", "highlighted": True}],
            {"1": [{"content": "h1"}]})
        obs = FakeObsidian()
        writes = run_archive(gl, obs, gl.get_all_links(), fetch=lambda url: None)
        assert writes == 1
        assert "3.Risorse/Articoli/Nuovo.md" in obs.files
        assert "3.Risorse/Full Document Contents/Articoli/Nuovo.md" not in obs.files

    def test_per_link_error_does_not_abort_run(self):
        class Boom(FakeGoodLinks):
            def get_highlights(self, link_id):
                if link_id == "1":
                    raise Exception("boom")
                return [{"content": "ok"}]
        gl = Boom(
            [{"id": "1", "title": "A", "url": "https://ex.com/a", "highlighted": True},
             {"id": "2", "title": "B", "url": "https://ex.com/b", "highlighted": True}],
            {})
        obs = FakeObsidian()
        writes = run_archive(gl, obs, gl.get_all_links(), fetch=no_fetch)
        assert writes == 2  # solo il link B
        assert "3.Risorse/Articoli/B.md" in obs.files
