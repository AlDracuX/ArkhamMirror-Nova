"""
Pattern Detection Engine

Algorithmic pattern detection across documents and events.
Works without LLM -- pure n-gram, temporal, and behavioral analysis.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any, Dict, List

_STOPWORDS = frozenset(
    "the a an and or but in on at to for of with by is was are were be been being "
    "have has had do does did will would could should may might shall can this that "
    "these those it its not no nor as if then than so such very too also just about "
    "into from up out all each every both few more most other some any only own same "
    "which who whom what when where how there here they them their he him his she her "
    "we our you your my".split()
)
_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def _has_content_word(words: List[str]) -> bool:
    return any(w not in _STOPWORDS for w in words)


class PatternEngine:
    """
    Detects repeated phrases (n-gram), temporal clusters, and
    behavioral patterns (escalation, avoidance, coordination).
    """

    def detect_ngram_patterns(
        self,
        documents: List[str],
        min_occurrences: int = 2,
        ngram_range: tuple = (2, 4),
    ) -> List[Dict[str, Any]]:
        """Detect repeated phrases across documents via n-gram frequency."""
        if not documents:
            return []
        ngram_global: Counter = Counter()
        ngram_doc_count: Counter = Counter()
        total_docs = len(documents)

        for doc in documents:
            tokens = _tokenize(doc)
            doc_ngrams: set = set()
            for n in range(ngram_range[0], ngram_range[1] + 1):
                for i in range(len(tokens) - n + 1):
                    gram = tuple(tokens[i : i + n])
                    if _has_content_word(list(gram)):
                        ngram_global[gram] += 1
                        doc_ngrams.add(gram)
            for gram in doc_ngrams:
                ngram_doc_count[gram] += 1

        results = []
        for gram, freq in ngram_global.most_common():
            if freq < min_occurrences:
                continue
            doc_count = ngram_doc_count[gram]
            sig = self.score_pattern(freq, doc_count, total_docs)
            results.append(
                {
                    "phrase": " ".join(gram),
                    "frequency": freq,
                    "doc_count": doc_count,
                    "significance": round(sig, 4),
                }
            )
        results.sort(key=lambda x: x["significance"], reverse=True)
        return results[:20]

    def detect_temporal_clusters(
        self,
        events: List[Dict[str, Any]],
        window_hours: int = 48,
        min_cluster_size: int = 3,
    ) -> List[Dict[str, Any]]:
        """Detect clusters of events within time windows."""
        if not events:
            return []
        sorted_events = sorted(events, key=lambda e: e["timestamp"])
        window = timedelta(hours=window_hours)
        clusters: List[Dict[str, Any]] = []
        used: set = set()

        for i, anchor in enumerate(sorted_events):
            if i in used:
                continue
            cluster_events = [anchor]
            cluster_indices = {i}
            for j in range(i + 1, len(sorted_events)):
                if j in used:
                    continue
                if sorted_events[j]["timestamp"] - anchor["timestamp"] <= window:
                    cluster_events.append(sorted_events[j])
                    cluster_indices.add(j)
                else:
                    break
            if len(cluster_events) >= min_cluster_size:
                used.update(cluster_indices)
                span_hours = max(
                    (cluster_events[-1]["timestamp"] - cluster_events[0]["timestamp"]).total_seconds() / 3600, 0.1
                )
                density = len(cluster_events) / span_hours
                clusters.append(
                    {
                        "start": cluster_events[0]["timestamp"],
                        "end": cluster_events[-1]["timestamp"],
                        "event_count": len(cluster_events),
                        "events": cluster_events,
                        "density": round(density, 4),
                        "significance": round(min(density / 5.0, 1.0), 4),
                    }
                )
        return clusters

    def detect_behavioral_patterns(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect escalation, avoidance, and coordination patterns."""
        if not events:
            return []
        results: List[Dict[str, Any]] = []
        results.extend(self._detect_escalation(events))
        results.extend(self._detect_avoidance(events))
        results.extend(self._detect_coordination(events))
        return results

    def _detect_escalation(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect increasing severity over time using rank correlation."""
        severed = [e for e in events if "severity" in e]
        if len(severed) < 3:
            return []
        sorted_ev = sorted(severed, key=lambda e: e["timestamp"])
        severities = [e["severity"] for e in sorted_ev]
        n = len(severities)
        ranks = list(range(n))
        mean_sev = sum(severities) / n
        mean_rank = sum(ranks) / n
        num = sum((s - mean_sev) * (r - mean_rank) for s, r in zip(severities, ranks))
        den_s = math.sqrt(sum((s - mean_sev) ** 2 for s in severities))
        den_r = math.sqrt(sum((r - mean_rank) ** 2 for r in ranks))
        if den_s == 0 or den_r == 0:
            return []
        correlation = num / (den_s * den_r)
        if correlation > 0.6:
            return [
                {
                    "pattern_subtype": "escalation",
                    "description": f"Severity escalation detected across {n} events (r={correlation:.2f})",
                    "significance": round(min(correlation, 1.0), 4),
                    "frequency": n,
                    "correlation": round(correlation, 4),
                    "events": sorted_ev,
                }
            ]
        return []

    def _detect_avoidance(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect patterns of non-response or delayed action."""
        response_required = [e for e in events if e.get("requires_response")]
        if not response_required:
            return []
        sorted_ev = sorted(events, key=lambda e: e["timestamp"])
        gaps = []
        for req_event in response_required:
            req_time = req_event["timestamp"]
            has_response = any(
                e["timestamp"] > req_time
                and not e.get("requires_response")
                and (e["timestamp"] - req_time) <= timedelta(days=14)
                for e in sorted_ev
            )
            if not has_response:
                gaps.append(req_event)
        if gaps:
            return [
                {
                    "pattern_subtype": "avoidance",
                    "description": f"{len(gaps)} event(s) requiring response received no timely reply",
                    "significance": round(min(len(gaps) / 3.0, 1.0), 4),
                    "frequency": len(gaps),
                    "gap_events": gaps,
                }
            ]
        return []

    def _detect_coordination(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect synchronized actions between entities."""
        entity_events = [e for e in events if "entity" in e]
        if len(entity_events) < 4:
            return []
        by_entity: Dict[str, List[Dict]] = defaultdict(list)
        for e in sorted(entity_events, key=lambda e: e["timestamp"]):
            by_entity[e["entity"]].append(e)
        entities = list(by_entity.keys())
        if len(entities) < 2:
            return []
        results = []
        prox_secs = 24 * 3600  # 24-hour proximity window
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                e1, e2 = entities[i], entities[j]
                co = sum(
                    1
                    for ev1 in by_entity[e1]
                    if any(
                        abs((ev1["timestamp"] - ev2["timestamp"]).total_seconds()) < prox_secs for ev2 in by_entity[e2]
                    )
                )
                min_ev = min(len(by_entity[e1]), len(by_entity[e2]))
                if min_ev >= 2 and co >= 2:
                    ratio = co / min_ev
                    if ratio >= 0.5:
                        results.append(
                            {
                                "pattern_subtype": "coordination",
                                "description": f"Entities '{e1}' and '{e2}' act within 24h of each other {co} times",
                                "significance": round(min(ratio * co / 4.0, 1.0), 4),
                                "frequency": co,
                                "entities": [e1, e2],
                            }
                        )
        return results

    def score_pattern(self, frequency: int, doc_spread: int, total_docs: int) -> float:
        """Score pattern by frequency and document spread. Returns 0.0-1.0."""
        if frequency == 0 or total_docs == 0:
            return 0.0
        freq_score = math.log(1 + frequency) / math.log(1 + 50)
        spread_score = doc_spread / total_docs
        return round(min(max(freq_score * spread_score, 0.0), 1.0), 4)
