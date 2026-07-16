import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import main
from main import escape_markdown, filter_recent, load_state, save_state, process_links


class TestEscapeMarkdown:
    def test_escapes_specials(self):
        assert escape_markdown("a_b*c") == r"a\_b\*c"

    def test_plain_text_unchanged(self):
        assert escape_markdown("Hello World") == "Hello World"

    def test_empty_string(self):
        assert escape_markdown("") == ""


class TestState:
    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "STATE_FILE", tmp_path / "missing.json")
        assert load_state() == {}

    def test_load_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text("not-json")
        monkeypatch.setattr(main, "STATE_FILE", state_file)
        assert load_state() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(main, "STATE_FILE", state_file)
        save_state({"1": ["mastodon"]})
        assert load_state() == {"1": ["mastodon"]}
        assert json.loads(state_file.read_text()) == {"1": ["mastodon"]}


def make_article(article_id="1", title="Titolo", url="https://example.com", notes="Note"):
    return {"id": article_id, "title": title, "url": url, "notes": notes}


class TestProcessLinks:
    def setup_method(self):
        self.calls = []

        def make_publisher(name, fail=False):
            def publish(title, link, notes):
                if fail:
                    raise Exception(f"{name} boom")
                self.calls.append((name, title, link, notes))
            return publish

        self.make_publisher = make_publisher

    def patch_state(self, tmp_path, monkeypatch, initial=None):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(main, "STATE_FILE", state_file)
        state = initial or {}
        save_state(state)
        return state

    def test_new_article_published_on_all_outputs(self, tmp_path, monkeypatch):
        state = self.patch_state(tmp_path, monkeypatch)
        publishers = {
            "mastodon": self.make_publisher("mastodon"),
            "telegram": self.make_publisher("telegram"),
            "hugo": self.make_publisher("hugo"),
        }
        failures = process_links([make_article()], state, publishers)
        assert failures == 0
        assert {c[0] for c in self.calls} == {"mastodon", "telegram", "hugo"}
        assert sorted(load_state()["1"]) == ["hugo", "mastodon", "telegram"]

    def test_already_published_article_skipped(self, tmp_path, monkeypatch):
        state = self.patch_state(
            tmp_path, monkeypatch, {"1": ["mastodon", "telegram", "hugo"]})
        publishers = {"mastodon": self.make_publisher("mastodon"),
                      "telegram": self.make_publisher("telegram"),
                      "hugo": self.make_publisher("hugo")}
        failures = process_links([make_article()], state, publishers)
        assert failures == 0
        assert self.calls == []

    def test_partial_failure_retries_only_missing_output(self, tmp_path, monkeypatch):
        state = self.patch_state(tmp_path, monkeypatch)
        publishers = {
            "mastodon": self.make_publisher("mastodon"),
            "telegram": self.make_publisher("telegram", fail=True),
            "hugo": self.make_publisher("hugo"),
        }
        failures = process_links([make_article()], state, publishers)
        assert failures == 1
        assert sorted(load_state()["1"]) == ["hugo", "mastodon"]

        # giro successivo: telegram funziona, gli altri non vengono duplicati
        self.calls.clear()
        publishers["telegram"] = self.make_publisher("telegram")
        state = load_state()
        failures = process_links([make_article()], state, publishers)
        assert failures == 0
        assert [c[0] for c in self.calls] == ["telegram"]
        assert sorted(load_state()["1"]) == ["hugo", "mastodon", "telegram"]

    def test_failing_output_does_not_block_others(self, tmp_path, monkeypatch):
        state = self.patch_state(tmp_path, monkeypatch)
        publishers = {
            "mastodon": self.make_publisher("mastodon", fail=True),
            "telegram": self.make_publisher("telegram"),
            "hugo": self.make_publisher("hugo"),
        }
        failures = process_links([make_article()], state, publishers)
        assert failures == 1
        assert {c[0] for c in self.calls} == {"telegram", "hugo"}

    def test_empty_fields_handled(self, tmp_path, monkeypatch):
        state = self.patch_state(tmp_path, monkeypatch)
        publishers = {"mastodon": self.make_publisher("mastodon")}
        article = {"id": "2", "title": None, "url": None, "notes": None}
        failures = process_links([article], state, publishers)
        assert failures == 0
        assert self.calls == [("mastodon", "", "", "")]


class TestTelegramMultiChat:
    def _helper(self, monkeypatch, chat_ids="111,222"):
        monkeypatch.setenv("TELEGRAM_BOT_API_KEY", "token")
        monkeypatch.setenv("TELEGRAM_CHAT_IDS", chat_ids)
        from telegram_helper import TelegramHelper
        return TelegramHelper()

    def test_invalid_chat_does_not_block_others(self, monkeypatch):
        helper = self._helper(monkeypatch)
        sent = []

        def fake_send(message, chat_id):
            if chat_id == "111":
                raise Exception("chat not found")
            sent.append(chat_id)

        monkeypatch.setattr(
            helper, "_TelegramHelper__send_telegram_message", fake_send)
        helper.send("ciao")  # non deve sollevare
        assert sent == ["222"]

    def test_all_chats_failing_raises(self, monkeypatch):
        helper = self._helper(monkeypatch)

        def fake_send(message, chat_id):
            raise Exception("boom")

        monkeypatch.setattr(
            helper, "_TelegramHelper__send_telegram_message", fake_send)
        try:
            helper.send("ciao")
            assert False, "doveva sollevare"
        except Exception as e:
            assert "tutte le chat" in str(e)


class TestFilterRecent:
    @staticmethod
    def iso(days_ago):
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')

    def test_old_articles_are_excluded(self):
        links = [
            {"id": "old", "modifiedAt": self.iso(30)},
            {"id": "new", "modifiedAt": self.iso(1)},
        ]
        assert [l["id"] for l in filter_recent(links)] == ["new"]

    def test_old_article_tagged_today_is_included(self):
        # il tagging aggiorna modifiedAt: articolo salvato mesi fa, taggato oggi
        links = [{"id": "1", "addedAt": self.iso(200), "modifiedAt": self.iso(0)}]
        assert len(filter_recent(links)) == 1

    def test_missing_timestamps_are_excluded(self):
        assert filter_recent([{"id": "x"}]) == []

    def test_falls_back_to_added_at(self):
        assert len(filter_recent([{"id": "1", "addedAt": self.iso(2)}])) == 1


class TestRenderTemplate:
    def test_empty_notes_leave_no_blank_gap(self):
        from main import render_template
        out = render_template("{title}\n{link}\n\n{notes}\n\n#news",
                              title="T", link="L", notes="")
        assert out == "T\nL\n\n#news"

    def test_filled_notes_kept(self):
        from main import render_template
        out = render_template("{title}\n\n{notes}", title="T", notes="la mia nota")
        assert out == "T\n\nla mia nota"


class TestGoodLinks:
    def test_first_note_is_oldest_highlight(self, monkeypatch):
        monkeypatch.setenv("GOODLINKS_TOKEN", "token")
        from goodlinks import GoodLinks

        payload = {"data": [
            {"content": "nota recente", "createdAt": "2026-06-14T06:01:48Z"},
            {"content": "prima nota", "createdAt": "2026-06-14T05:53:22Z"},
        ]}
        monkeypatch.setattr(
            "goodlinks.requests.get",
            lambda url, headers, params: MagicMock(status_code=200, json=lambda: payload))
        assert GoodLinks().get_first_note("abc") == "prima nota"

    def test_first_note_empty_without_highlights(self, monkeypatch):
        monkeypatch.setenv("GOODLINKS_TOKEN", "token")
        from goodlinks import GoodLinks
        monkeypatch.setattr(
            "goodlinks.requests.get",
            lambda url, headers, params: MagicMock(status_code=200, json=lambda: {"data": []}))
        assert GoodLinks().get_first_note("abc") == ""

    def test_paginated_response_is_flattened(self, monkeypatch):
        monkeypatch.setenv("GOODLINKS_TOKEN", "token")
        from goodlinks import GoodLinks

        pages = [
            {"data": [{"id": "1"}, {"id": "2"}], "hasMore": True},
            {"data": [{"id": "3"}], "hasMore": False},
        ]
        offsets = []

        def fake_get(url, headers, params):
            offsets.append(params["offset"])
            response = MagicMock()
            response.json.return_value = pages.pop(0)
            return response

        monkeypatch.setattr("goodlinks.requests.get", fake_get)
        links = GoodLinks().get_links_to_publish()
        assert [l["id"] for l in links] == ["1", "2", "3"]
        assert offsets == [0, 2]


class TestHugoHelper:
    def _helper(self, monkeypatch):
        monkeypatch.setenv("BLOG_REPO", "owner/blog")
        monkeypatch.setenv("BLOG_REPO_TOKEN", "token")
        from hugo_helper import HugoHelper
        return HugoHelper()

    def test_publish_creates_post_via_api(self, monkeypatch):
        import base64
        helper = self._helper(monkeypatch)
        puts = []

        def fake_get(url, headers):
            return MagicMock(status_code=404)

        def fake_put(url, headers, json):
            puts.append((url, json))
            return MagicMock(status_code=201)

        monkeypatch.setattr("hugo_helper.requests.get", fake_get)
        monkeypatch.setattr("hugo_helper.requests.put", fake_put)
        helper.publish("Un titolo di prova!", "https://example.com", "note")

        url, payload = puts[0]
        assert url.endswith("/repos/owner/blog/contents/content/blog/un-titolo-di-prova.md")
        content = base64.b64decode(payload["content"]).decode()
        assert 'title: "Un titolo di prova!"' in content
        assert "- Link condivisi" in content
        assert "[Leggi l'articolo originale](https://example.com)" in content

    def test_publish_is_idempotent_on_existing_file(self, monkeypatch):
        helper = self._helper(monkeypatch)
        monkeypatch.setattr(
            "hugo_helper.requests.get", lambda url, headers: MagicMock(status_code=200))
        monkeypatch.setattr(
            "hugo_helper.requests.put",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("non deve chiamare PUT")))
        helper.publish("Un titolo di prova!", "https://example.com", "note")

    def test_api_error_raises(self, monkeypatch):
        helper = self._helper(monkeypatch)
        monkeypatch.setattr(
            "hugo_helper.requests.get", lambda url, headers: MagicMock(status_code=404))
        monkeypatch.setattr(
            "hugo_helper.requests.put",
            lambda url, headers, json: MagicMock(status_code=422, text="boom"))
        try:
            helper.publish("Titolo", "https://example.com", "note")
            assert False, "doveva sollevare"
        except Exception as e:
            assert "422" in str(e)

    def test_slugify(self):
        from hugo_helper import slugify
        assert slugify("Ciao, Mondo! 2026") == "ciao-mondo-2026"
        assert slugify("***") == "senza-titolo"
