"""arXiv tools for career_agent — search, fetch, and summarise papers."""

from __future__ import annotations

import asyncio
from typing import Any

import arxiv
import structlog
from opentelemetry import trace

log = structlog.get_logger(__name__)

# Each file gets its own tracer. The name shows up as the span's "library" in Cloud Trace.
tracer = trace.get_tracer(__name__)

_DEFAULT_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "stat.ML"]
_MAX_RESULTS = 20


def search_arxiv_papers(
    query: str,
    categories: list[str] | None = None,
    max_results: int = 10,
    sort_by: str = "submittedDate",
) -> list[dict[str, Any]]:
    """Search arXiv for papers matching a query.

    Args:
        query: Free-text search string, e.g. "LLM agents tool use".
        categories: arXiv categories to filter on, e.g. ["cs.AI", "cs.LG"].
        max_results: Maximum number of results to return (cap: 20).
        sort_by: "submittedDate" | "relevance" | "lastUpdatedDate".

    Returns:
        List of paper dicts with id, title, authors, abstract, url, published.
    """
    # start_as_current_span creates a span and makes it the "current" span for this
    # thread. Any child spans created inside this block are automatically nested under it.
    with tracer.start_as_current_span("tool.arxiv.search_papers") as span:
        # Attributes are key/value pairs visible in Cloud Trace's span detail panel.
        # Use them to record inputs so you can debug what the agent was searching for.
        span.set_attribute("arxiv.query", query)
        span.set_attribute("arxiv.max_results", max_results)
        span.set_attribute("arxiv.sort_by", sort_by)

        cats = categories or _DEFAULT_CATEGORIES
        cat_filter = " OR ".join(f"cat:{c}" for c in cats)
        full_query = f"({query}) AND ({cat_filter})"

        sort_criterion = {
            "submittedDate": arxiv.SortCriterion.SubmittedDate,
            "relevance": arxiv.SortCriterion.Relevance,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        }.get(sort_by, arxiv.SortCriterion.SubmittedDate)

        client = arxiv.Client()
        client.query_url_format = "https://export.arxiv.org/api/query?{}"
        search = arxiv.Search(
            query=full_query,
            max_results=min(max_results, _MAX_RESULTS),
            sort_by=sort_criterion,
        )

        results = []
        for paper in client.results(search):
            results.append(
                {
                    "id": paper.entry_id,
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors[:5]],
                    "abstract": paper.summary[:800],
                    "url": paper.entry_id,
                    "pdf_url": paper.pdf_url,
                    "published": paper.published.isoformat() if paper.published else "",
                    "categories": paper.categories,
                }
            )

        # Record outputs too — now you can see query → result count in the trace.
        span.set_attribute("arxiv.results_count", len(results))
        log.info("arxiv.search", query=query, found=len(results))
        return results


def fetch_daily_arxiv_digest(
    categories: list[str] | None = None,
    max_papers: int = 15,
) -> list[dict[str, Any]]:
    """Fetch today's top papers from specified arXiv categories.

    Returns the most recent papers sorted by submission date — ideal for
    a morning digest.
    """
    with tracer.start_as_current_span("tool.arxiv.daily_digest") as span:
        span.set_attribute("arxiv.max_papers", max_papers)

        cats = categories or _DEFAULT_CATEGORIES
        cat_query = " OR ".join(f"cat:{c}" for c in cats)

        client = arxiv.Client()
        client.query_url_format = "https://export.arxiv.org/api/query?{}"
        search = arxiv.Search(
            query=cat_query,
            max_results=max_papers,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )

        papers = []
        for paper in client.results(search):
            papers.append(
                {
                    "id": paper.entry_id,
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors[:3]],
                    "abstract_short": paper.summary[:400],
                    "url": paper.entry_id,
                    "published": paper.published.isoformat() if paper.published else "",
                    "categories": paper.categories,
                }
            )

        span.set_attribute("arxiv.results_count", len(papers))
        return papers


def build_paper_summary_prompt(paper: dict[str, Any]) -> str:
    """Return a structured prompt to summarize a paper for skill-gap analysis."""
    return f"""Summarise this research paper for an AI professional building career expertise:

Title: {paper["title"]}
Authors: {", ".join(paper.get("authors", []))}
Published: {paper.get("published", "unknown")}
Abstract: {paper.get("abstract", paper.get("abstract_short", ""))}

Provide:
1. Core contribution (2 sentences)
2. Practical takeaway for an AI engineer (1 sentence)
3. Skill areas this paper touches (bullet list: e.g. RAG, fine-tuning, agentic systems)
4. Relevance to career advancement: HIGH / MEDIUM / LOW with 1-line reason
"""
