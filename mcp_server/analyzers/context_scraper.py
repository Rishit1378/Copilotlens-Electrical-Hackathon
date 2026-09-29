"""
CopilotLens - Context Scraper & Semantic Knowledge Base Engine
==============================================================
Scrapes Jira tickets, Confluence pages, and Bitbucket Pull Requests
matching target topics or keywords, filters them using BM25 semantic
relevance scoring, and stores structured context in an SQLite database.
"""

import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# HTML tag cleaner for Confluence storage format
TAG_RE = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    """Removes HTML tags and unescapes common entities."""
    if not text:
        return ""
    cleaned = TAG_RE.sub(" ", text)
    cleaned = (
        cleaned.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric terms for semantic matching."""
    if not text:
        return []
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_]{2,}", text)]


class BM25Ranker:
    """
    Lightweight, dependency-free BM25 semantic ranking engine.
    Ensures extracted tickets, pages, and PRs are genuinely relevant
    to the topic rather than incidental occurrences of the keyword.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def rank(
        self, query_terms: List[str], documents: List[Dict[str, Any]], field: str = "text"
    ) -> List[Tuple[float, Dict[str, Any]]]:
        if not documents or not query_terms:
            return [(1.0, doc) for doc in documents]

        doc_tokens = [tokenize(doc.get(field, "")) for doc in documents]
        n_docs = len(documents)
        avg_dl = sum(len(d) for d in doc_tokens) / max(1, n_docs)

        # Document frequencies
        df = {}
        for term in query_terms:
            df[term] = sum(1 for d in doc_tokens if term in d)

        # Calculate scores
        scored_docs = []
        for i, doc in enumerate(documents):
            score = 0.0
            tokens = doc_tokens[i]
            dl = len(tokens)
            token_counts = {}
            for t in tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

            for term in query_terms:
                freq = token_counts.get(term, 0)
                if freq == 0:
                    continue
                # Term IDF
                term_df = df.get(term, 0)
                idf = math.log((n_docs - term_df + 0.5) / (term_df + 0.5) + 1.0)
                # BM25 tf
                tf = (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * (dl / avg_dl if avg_dl else 1.0))
                )
                score += idf * tf

            # Title booster: if query term is in doc title/key, boost score
            title_tokens = set(tokenize(doc.get("title", "") + " " + doc.get("key", "")))
            for term in query_terms:
                if term in title_tokens:
                    score += 2.5

            scored_docs.append((round(score, 4), doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return scored_docs


class ContextDatabase:
    """SQLite storage for scraped and filtered Atlassian context items."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS context_items (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    key_or_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    snippet TEXT,
                    raw_content TEXT,
                    url TEXT,
                    author TEXT,
                    status TEXT,
                    created_at TEXT,
                    scraped_at TEXT,
                    query_topic TEXT,
                    relevance_score REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query_topic ON context_items(query_topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_type ON context_items(source_type)")
            conn.commit()

    def save_items(self, items: List[Dict[str, Any]], query_topic: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            for item in items:
                item_id = f"{item['source_type']}:{item['key_or_id']}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO context_items (
                        id, source_type, key_or_id, title, snippet, raw_content,
                        url, author, status, created_at, scraped_at, query_topic, relevance_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        item.get("source_type", "unknown"),
                        str(item.get("key_or_id", "")),
                        item.get("title", ""),
                        item.get("snippet", ""),
                        item.get("raw_content", ""),
                        item.get("url", ""),
                        item.get("author", ""),
                        item.get("status", ""),
                        str(item.get("created_at", "")),
                        now,
                        query_topic.lower(),
                        float(item.get("relevance_score", 0.0)),
                    ),
                )
            conn.commit()

    def get_context_for_topic(self, topic: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM context_items
                WHERE query_topic = ?
                ORDER BY relevance_score DESC
                LIMIT ?
                """,
                (topic.lower(), limit),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM context_items").fetchone()[0]
            by_source = conn.execute(
                "SELECT source_type, COUNT(*) FROM context_items GROUP BY source_type"
            ).fetchall()
            topics = conn.execute(
                "SELECT DISTINCT query_topic FROM context_items"
            ).fetchall()
            return {
                "total_items": total,
                "by_source": {row[0]: row[1] for row in by_source},
                "topics_indexed": [row[0] for row in topics if row[0]],
            }


class ContextScraper:
    """
    Orchestrates live scraping across Jira, Confluence, and Bitbucket,
    applies semantic relevance ranking, and stores results into SQLite.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        db_path = self.repo_path / ".copilotlens_context.db"
        self.db = ContextDatabase(db_path)
        self.ranker = BM25Ranker()

    def scrape_and_index_context(
        self,
        topic: str,
        max_jira: int = 15,
        max_confluence: int = 10,
        max_bitbucket: int = 15,
        min_relevance_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Scrapes Jira, Confluence, and Bitbucket for a given keyword/topic,
        applies semantic relevance ranking, stores into SQLite, and returns
        a rich structured summary for Copilot context building.
        """
        query_terms = tokenize(topic)
        if not query_terms:
            return {"error": True, "reason": "No valid search terms provided."}

        try:
            from integrations.atlassian.jira import jira_manager
            from integrations.atlassian.confluence import confluence_manager
            from integrations.atlassian.bitbucket import bitbucket_manager
        except ImportError:
            from mcp_server.integrations.atlassian.jira import jira_manager
            from mcp_server.integrations.atlassian.confluence import confluence_manager
            from mcp_server.integrations.atlassian.bitbucket import bitbucket_manager

        jira_candidates: List[Dict[str, Any]] = []
        confluence_candidates: List[Dict[str, Any]] = []
        bitbucket_candidates: List[Dict[str, Any]] = []

        # ── 1. Scrape Jira Tickets ──────────────────────────────────────────
        try:
            # Query Jira with summary and description search
            clean_q = topic.replace('"', '\\"')
            jql = f'(summary ~ "{clean_q}" OR text ~ "{clean_q}") ORDER BY updated DESC'
            jira_res = jira_manager.client.request(
                "GET", "/rest/api/2/search", params={"jql": jql, "maxResults": max_jira * 2}
            )
            for raw in jira_res.get("issues", []):
                fields = raw.get("fields", {})
                desc = fields.get("description") or ""
                summary = fields.get("summary") or ""
                key = raw.get("key", "")
                text_corpus = f"{key} {summary}\n{desc}"
                jira_candidates.append(
                    {
                        "source_type": "jira",
                        "key_or_id": key,
                        "title": summary,
                        "snippet": desc[:300].strip(),
                        "raw_content": desc,
                        "text": text_corpus,
                        "url": f"{jira_manager.client.get_base_url()}/browse/{key}",
                        "author": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
                        "status": (fields.get("status") or {}).get("name", "Unknown"),
                        "created_at": fields.get("created", ""),
                    }
                )
        except Exception as e:
            print(f"[ContextScraper] Jira scrape error: {e}")

        # ── 2. Scrape Confluence Pages ──────────────────────────────────────
        try:
            clean_q = topic.replace('"', '\\"')
            cql = f'title ~ "{clean_q}" OR text ~ "{clean_q}" order by lastModified desc'
            conf_res = confluence_manager.client.request(
                "GET",
                "/rest/api/content/search",
                params={
                    "cql": cql,
                    "limit": max_confluence * 2,
                    "expand": "body.storage,version,space,history",
                },
            )
            for page in conf_res.get("results", []):
                title = page.get("title", "")
                raw_html = page.get("body", {}).get("storage", {}).get("value", "")
                plain_body = clean_html(raw_html)
                page_id = page.get("id", "")
                text_corpus = f"{title}\n{plain_body}"
                confluence_candidates.append(
                    {
                        "source_type": "confluence",
                        "key_or_id": str(page_id),
                        "title": title,
                        "snippet": plain_body[:300].strip(),
                        "raw_content": plain_body[:4000],  # store substantial body
                        "text": text_corpus,
                        "url": f"{confluence_manager.client.get_base_url()}{page.get('_links', {}).get('webui', '')}",
                        "author": page.get("space", {}).get("name", "Confluence Space"),
                        "status": f"Version {page.get('version', {}).get('number', 1)}",
                        "created_at": page.get("history", {}).get("createdDate", ""),
                    }
                )
        except Exception as e:
            print(f"[ContextScraper] Confluence scrape error: {e}")

        # ── 3. Scrape Bitbucket Pull Requests ──────────────────────────────
        try:
            proj = os.getenv("BITBUCKET_PROJECT_KEY") or "IESD"
            repo = os.getenv("BITBUCKET_REPO_SLUG") or "iesd-26"
            bb_res = bitbucket_manager.client.request(
                "GET",
                f"/rest/api/1.0/projects/{proj}/repos/{repo}/pull-requests",
                params={"limit": 50, "state": "ALL"},
            )
            for pr in bb_res.get("values", []):
                pr_id = str(pr.get("id", ""))
                title = pr.get("title", "")
                desc = pr.get("description", "")
                author_name = (pr.get("author", {}).get("user") or {}).get("displayName", "")
                src_branch = (pr.get("fromRef") or {}).get("displayId", "")
                tgt_branch = (pr.get("toRef") or {}).get("displayId", "")
                text_corpus = f"PR {pr_id} {title} {src_branch} {tgt_branch}\n{desc}"
                
                # Check for match in title, description, or branch names
                pr_tokens = set(tokenize(text_corpus))
                if any(t in pr_tokens for t in query_terms):
                    bitbucket_candidates.append(
                        {
                            "source_type": "bitbucket",
                            "key_or_id": pr_id,
                            "title": title,
                            "snippet": desc[:300].strip(),
                            "raw_content": desc,
                            "text": text_corpus,
                            "url": (pr.get("links", {}).get("self", [{}])[0] or {}).get("href", ""),
                            "author": author_name,
                            "status": pr.get("state", "OPEN"),
                            "created_at": str(pr.get("createdDate", "")),
                        }
                    )
        except Exception as e:
            print(f"[ContextScraper] Bitbucket scrape error: {e}")

        # ── 4. Semantic BM25 Relevance Filtering ───────────────────────────
        filtered_jira: List[Dict[str, Any]] = []
        filtered_confluence: List[Dict[str, Any]] = []
        filtered_bitbucket: List[Dict[str, Any]] = []

        if jira_candidates:
            ranked_jira = self.ranker.rank(query_terms, jira_candidates, field="text")
            for score, doc in ranked_jira:
                if score >= min_relevance_threshold or len(filtered_jira) < 3:
                    doc_copy = dict(doc)
                    doc_copy["relevance_score"] = score
                    filtered_jira.append(doc_copy)
                    if len(filtered_jira) >= max_jira:
                        break

        if confluence_candidates:
            ranked_conf = self.ranker.rank(query_terms, confluence_candidates, field="text")
            for score, doc in ranked_conf:
                if score >= min_relevance_threshold or len(filtered_confluence) < 3:
                    doc_copy = dict(doc)
                    doc_copy["relevance_score"] = score
                    filtered_confluence.append(doc_copy)
                    if len(filtered_confluence) >= max_confluence:
                        break

        if bitbucket_candidates:
            ranked_bb = self.ranker.rank(query_terms, bitbucket_candidates, field="text")
            for score, doc in ranked_bb:
                if score >= min_relevance_threshold or len(filtered_bitbucket) < 3:
                    doc_copy = dict(doc)
                    doc_copy["relevance_score"] = score
                    filtered_bitbucket.append(doc_copy)
                    if len(filtered_bitbucket) >= max_bitbucket:
                        break

        all_filtered = filtered_jira + filtered_confluence + filtered_bitbucket

        # ── 5. Persist to SQLite Database ──────────────────────────────────
        if all_filtered:
            self.db.save_items(all_filtered, query_topic=topic)

        # ── 6. Assemble Formatted Context Report for LLM/User ──────────────
        report_md = self._build_markdown_report(
            topic, filtered_jira, filtered_confluence, filtered_bitbucket
        )

        return {
            "topic": topic,
            "total_relevant_items": len(all_filtered),
            "jira_count": len(filtered_jira),
            "confluence_count": len(filtered_confluence),
            "bitbucket_count": len(filtered_bitbucket),
            "database_path": str(self.db.db_path),
            "jira_items": [
                {k: v for k, v in item.items() if k not in ("text", "raw_content")}
                for item in filtered_jira
            ],
            "confluence_items": [
                {k: v for k, v in item.items() if k not in ("text", "raw_content")}
                for item in filtered_confluence
            ],
            "bitbucket_items": [
                {k: v for k, v in item.items() if k not in ("text", "raw_content")}
                for item in filtered_bitbucket
            ],
            "context_markdown": report_md,
        }

    def _build_markdown_report(
        self,
        topic: str,
        jira_items: List[Dict[str, Any]],
        confluence_items: List[Dict[str, Any]],
        bitbucket_items: List[Dict[str, Any]],
    ) -> str:
        lines = [
            f"# 📚 Extensive Context Intelligence for `{topic}`",
            f"*Semantically scraped across Jira, Confluence, and Bitbucket. Stored in SQLite database.*",
            "",
        ]

        if jira_items:
            lines.append(f"## 🎫 Jira Tickets ({len(jira_items)})")
            for it in jira_items:
                score = it.get("relevance_score", 0.0)
                lines.append(
                    f"- **[{it['key_or_id']}]({it['url']})**: **{it['title']}** "
                    f"`{it.get('status', '')}` *(Relevance: {score})*"
                )
                if it.get("snippet"):
                    lines.append(f"  > {it['snippet'][:180]}...")
            lines.append("")

        if confluence_items:
            lines.append(f"## 📖 Confluence Architecture & Design Pages ({len(confluence_items)})")
            for it in confluence_items:
                score = it.get("relevance_score", 0.0)
                lines.append(
                    f"- **[{it['title']}]({it['url']})** *(Relevance: {score})*"
                )
                if it.get("snippet"):
                    lines.append(f"  > {it['snippet'][:180]}...")
            lines.append("")

        if bitbucket_items:
            lines.append(f"## 🔀 Bitbucket Pull Requests ({len(bitbucket_items)})")
            for it in bitbucket_items:
                score = it.get("relevance_score", 0.0)
                lines.append(
                    f"- **[PR #{it['key_or_id']}]({it['url']})**: **{it['title']}** "
                    f"`{it.get('status', '')}` *(Relevance: {score})* — Author: {it.get('author', 'Unknown')}"
                )
                if it.get("snippet"):
                    lines.append(f"  > {it['snippet'][:180]}...")
            lines.append("")

        if not (jira_items or confluence_items or bitbucket_items):
            lines.append(f"No high-relevance items found for `{topic}` across Atlassian services.")

        return "\n".join(lines)
