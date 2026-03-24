"""MkDocs macros module: auto-generate article list from docs directory."""

import os
import re


def define_env(env):
    """Define macros for mkdocs-macros-plugin."""

    @env.macro
    def article_list():
        """Generate a markdown list of all articles in docs/."""
        docs_dir = env.conf["docs_dir"]
        articles = []

        for filename in sorted(os.listdir(docs_dir)):
            if not filename.endswith(".md") or filename in ("index.md", "CNAME"):
                continue

            filepath = os.path.join(docs_dir, filename)
            title = None
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    match = re.match(r"^#\s+(.+)", line)
                    if match:
                        title = match.group(1).strip()
                        break

            if not title:
                title = filename.replace(".md", "").replace("-", " ").title()

            url = filename
            articles.append(f"- [{title}]({url})")

        return "\n".join(articles)
