# tools/analysis/cluster_engine.py

from __future__ import annotations

import json
import uuid
from collections import Counter
from typing import Optional

import numpy as np

from core.state import GraphState
from schemas.issue_schema import (
    IssueCluster, IssueReport, IssueCategory, IssueSeverity,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)

# Severity ordering for dominant_severity computation
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_SEV_ORDER = ["critical", "high", "medium", "low"]




# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def clustering_node(state: GraphState) -> dict:
    """
    LangGraph node. Receives verified issues from analysis_node,
    clusters them with sentence-transformers + HDBSCAN.
    Output (issue_clusters) is passed to the supervisor's recommender_profile_node.
    """
    # Use pre-verified issues when available; fall back to raw simulation issues
    verified_issues: list[IssueReport] = state.get("verified_issues") or []
    if not verified_issues:
        # Fallback: flatten all issues from simulation results
        for result in state.get("simulation_results", []):
            verified_issues.extend(result.issues)

    logger.info("clustering.start", total_issues=len(verified_issues))

    if not verified_issues:
        logger.warning("clustering.no_issues_found")
        return {"issue_clusters": []}

    # Cluster issues — results handed back to supervisor for recommender profile generation
    clusters = _cluster_issues(verified_issues)
    logger.info("clustering.complete", clusters=len(clusters))

    return {"issue_clusters": clusters}


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def _issue_to_text(issue: IssueReport) -> str:
    """
    Build a rich embedding input from an issue.
    Combines title + description + category + wcag + affected element.
    More signal → better clustering quality.
    """
    parts = [issue.title, issue.description[:300]]
    if issue.wcag_criterion:
        parts.append(issue.wcag_criterion)
    parts.append(str(issue.category))
    if issue.affected_element:
        parts.append(issue.affected_element)
    return " | ".join(p for p in parts if p)


def _embed_issues(issues: list[IssueReport]) -> np.ndarray:
    """
    Embed all issues using sentence-transformers all-MiniLM-L6-v2.
    Returns shape (N, embedding_dim).
    """
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [_issue_to_text(iss) for iss in issues]
    embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
    return np.array(embeddings)


def _run_hdbscan(embeddings: np.ndarray, n_issues: int) -> np.ndarray:
    """
    Run HDBSCAN on the embeddings.
    min_cluster_size scales with corpus size but never below 2.
    Returns integer label array; -1 = noise (will become singletons).
    """
    import hdbscan
    # Tune min_cluster_size: small for few issues, larger for many
    min_cs = max(2, n_issues // 6)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cs,
        min_samples=1,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    clusterer.fit(embeddings)
    return clusterer.labels_


def _dominant(values: list[str], rank_map: Optional[dict] = None) -> str:
    """Return the most common value; if rank_map provided, break ties by rank."""
    if not values:
        return "unknown"
    if rank_map:
        return max(set(values), key=lambda v: (values.count(v), rank_map.get(v, 0)))
    return Counter(values).most_common(1)[0][0]


def _cluster_issues(issues: list[IssueReport]) -> list[IssueCluster]:
    """
    Full clustering pipeline: embed → HDBSCAN → group → label.
    Falls back to category-based grouping if embeddings fail.
    """
    n = len(issues)

    # For very small sets (≤ 2), skip embedding overhead
    if n <= 2:
        return _category_fallback(issues)

    try:
        embeddings = _embed_issues(issues)
        labels     = _run_hdbscan(embeddings, n)
    except Exception as e:
        logger.warning("clustering.embedding_failed", error=str(e))
        return _category_fallback(issues)

    # Group issues by cluster label
    groups: dict[int, list[IssueReport]] = {}
    for issue, label in zip(issues, labels):
        groups.setdefault(label, []).append(issue)

    clusters: list[IssueCluster] = []
    cluster_idx = 1

    # Real clusters first (label != -1), then noise singletons
    for label in sorted(groups.keys()):
        group = groups[label]
        clusters.append(_make_cluster(group, f"cluster_{cluster_idx}"))
        cluster_idx += 1

    logger.info(
        "clustering.hdbscan_done",
        n_issues=n,
        n_clusters=sum(1 for l in groups if l != -1),
        n_noise=len(groups.get(-1, [])),
    )
    return clusters


def _make_cluster(issues: list[IssueReport], cluster_id: str) -> IssueCluster:
    """Derive all cluster metadata deterministically from its member issues."""
    severities = [str(iss.severity) for iss in issues]
    categories = [str(iss.category) for iss in issues]

    dom_sev = _dominant(severities, _SEV_RANK)
    dom_cat = _dominant(categories)

    affected_personas  = list(dict.fromkeys(iss.persona_id for iss in issues))
    affected_elements  = list(dict.fromkeys(
        iss.affected_element for iss in issues if iss.affected_element
    ))

    # Label: most common category + top severity + first title as anchor
    anchor = issues[0].title if issues else "Issues"
    label  = f"{dom_cat.capitalize()} — {dom_sev} ({len(issues)} issue{'s' if len(issues) > 1 else ''})"

    # Representative description: aggregate the titles
    titles = "; ".join(dict.fromkeys(iss.title for iss in issues[:5]))
    rep    = f"{len(issues)} {dom_cat} issue(s) at {dom_sev} severity. Titles: {titles}."

    return IssueCluster(
        cluster_id=cluster_id,
        cluster_label=label,
        issues=issues,
        dominant_category=IssueCategory(dom_cat),
        dominant_severity=IssueSeverity(dom_sev),
        affected_personas=affected_personas,
        affected_elements=affected_elements,
        representative_description=rep,
        issue_count=len(issues),
    )


def _category_fallback(issues: list[IssueReport]) -> list[IssueCluster]:
    """
    Simple grouping by category when embedding is unavailable.
    Used for very small issue sets or on embedding failure.
    """
    groups: dict[str, list[IssueReport]] = {}
    for iss in issues:
        groups.setdefault(str(iss.category), []).append(iss)

    return [
        _make_cluster(group, f"cluster_{i+1}")
        for i, group in enumerate(groups.values())
    ]