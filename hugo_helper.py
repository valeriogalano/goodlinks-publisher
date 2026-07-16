import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("hugo")


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug or 'senza-titolo'


class HugoHelper:
    def __init__(self):
        self.repo_path = Path(os.environ["BLOG_REPO_PATH"])
        # ponytail: sezione content/links/ fissa; se il blog vorrà un'altra
        # sezione o un archetype diverso, basta cambiare qui
        self.content_dir = self.repo_path / "content" / "links"

        logger.debug("Hugo helper inizializzato!")

    def __git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise Exception(f"git {' '.join(args)} fallito: {result.stderr.strip()}")
        return result.stdout

    def publish(self, title: str, link: str, notes: str):
        """Scrive il post nel repo del blog e fa commit + push.

        Idempotente: se il file esiste già (push fallito al giro precedente),
        non riscrive né ricommitta, ritenta solo il push.
        """
        self.__git("pull", "--ff-only")

        post_path = self.content_dir / f"{slugify(title)}.md"
        if not post_path.exists():
            self.content_dir.mkdir(parents=True, exist_ok=True)
            date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S%z')
            escaped_title = title.replace('"', '\\"')
            frontmatter = (
                "---\n"
                f'title: "{escaped_title}"\n'
                f"date: {date}\n"
                f"link: {link}\n"
                "---\n"
            )
            post_path.write_text(frontmatter + f"\n{notes}\n", encoding="utf-8")
            relative_path = post_path.relative_to(self.repo_path)
            self.__git("add", str(relative_path))
            self.__git("commit", "-m", f"Add shared link: {title}")
            logger.debug(f"Post creato e committato: {relative_path}")
        else:
            logger.debug(f"Post già presente, ritento solo il push: {post_path.name}")

        self.__git("push")
