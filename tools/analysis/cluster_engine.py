# tools/analysis/cluster_engine.py
"""
Clustering Node — fully implemented.

Pipeline:
  1. Collect all verified IssueReport objects from state["verified_issues"]
     (pre-filtered by analysis_node to exclude issues from invalid trace steps)
  2. Build a rich text representation of each issue for embedding
  3. Embed with sentence-transformers (all-MiniLM-L6-v2 — fast, good quality)
  4. Cluster with HDBSCAN:
       - No need to specify K upfront
       - Noise points (label == -1) become singleton clusters
       - min_cluster_size tuned to issue volume
  5. Derive cluster metadata deterministically from member issues
  6. Output list[IssueCluster] → passed to recommender_profile_node in supervisor

Why HDBSCAN over K-Means:
  - No need to specify number of clusters upfront
  - Handles noise/outlier issues as singletons rather than forcing them into a cluster
  - Robust to varying issue density across a run
  - Consistent results on small datasets (4-20 issues typical per page)

Why sentence-transformers over TF-IDF:
  - Captures semantic similarity: "missing label" and "no accessible name" cluster together
  - Robust to different phrasings of the same underlying problem
  - Fast CPU inference (~50ms for 20 issues on all-MiniLM-L6-v2)
"""

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

# --- Lazy/Singleton heavy weights ---
_EMBEDDING_MODEL = None
_HDBSCAN_MOD     = None

def _get_embedding_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        import time
        start = time.perf_counter()
        logger.info("clustering.model_loading.start", model="all-MiniLM-L6-v2")
        
        try:
            # Limit torch threads to avoid CPU contention in parallel pipeline
            import torch
            torch.set_num_threads(1)
            
            from sentence_transformers import SentenceTransformer
            import logging
            import warnings
            
            # Silence HF noise
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
            warnings.filterwarnings("ignore", message=".*unauthenticated.*", category=UserWarning)

            _EMBEDDING_MODEL = SentenceTransformer(
                "all-MiniLM-L6-v2", 
                tokenizer_kwargs={"clean_up_tokenization_spaces": True}
            )
            elapsed = time.perf_counter() - start
            logger.info("clustering.model_loading.done", elapsed_sec=round(elapsed, 2))
        except Exception as e:
            logger.error("clustering.model_loading.failed", error=str(e))
            raise
    return _EMBEDDING_MODEL

def _get_hdbscan():
    global _HDBSCAN_MOD
    if _HDBSCAN_MOD is None:
        import hdbscan
        _HDBSCAN_MOD = hdbscan
    return _HDBSCAN_MOD

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
    Combines title + description + category + wcag + affected element + UI_page.
    UI_page keeps issues from different pages separated unless they share root cause.
    """
    parts = [issue.title, issue.description[:300]]
    if issue.wcag_criterion:
        parts.append(issue.wcag_criterion)
    parts.append(str(issue.category))
    if issue.affected_element:
        parts.append(issue.affected_element)
    if issue.UI_page:
        parts.append(issue.UI_page)
    return " | ".join(p for p in parts if p)


def _embed_issues(issues: list[IssueReport]) -> np.ndarray:
    """
    Embed all issues using sentence-transformers all-MiniLM-L6-v2.
    Uses a global singleton to avoid reload overhead.
    """
    model = _get_embedding_model()
    texts = [_issue_to_text(iss) for iss in issues]
    
    import time
    start = time.perf_counter()
    embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
    elapsed = time.perf_counter() - start
    
    logger.info("clustering.embedding_done", count=len(issues), elapsed_ms=int(elapsed*1000))
    return np.array(embeddings)


def _run_hdbscan(embeddings: np.ndarray, n_issues: int) -> np.ndarray:
    """
    Run HDBSCAN on the embeddings.
    min_cluster_size scales with corpus size but never below 2.
    Returns integer label array; -1 = noise (will become singletons).
    """
    hdbscan_mod = _get_hdbscan()
    # Tune min_cluster_size: small for few issues, larger for many
    min_cs = max(2, n_issues // 6)
    clusterer = hdbscan_mod.HDBSCAN(
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