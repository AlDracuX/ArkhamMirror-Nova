# ACH SHARD AGENTS

## OVERVIEW
Analysis of Competing Hypotheses (ACH) shard for structured intelligence analysis and AI-assisted hypothesis testing.

## WHERE TO LOOK
| Component | Location | Role |
|-----------|----------|------|
| Scoring Engine | `arkham_shard_ach/scoring.py` | Implementation of ACH inconsistency-based ranking and diagnosticity. |
| AI Integration | `arkham_shard_ach/llm.py` | Devil's Advocate, Premortem, and Scenario generation logic. |
| Matrix Logic | `arkham_shard_ach/matrix.py` | Core state management for hypotheses, evidence, and rating grids. |
| Corpus Search | `arkham_shard_ach/corpus.py` | Vector-based evidence extraction and duplicate detection. |
| Persistence | `arkham_shard_ach/models.py` | SQLAlchemy/Pydantic models for matrix and scenario tree persistence. |
| AI Prompts | `arkham_shard_ach/prompts.py` | Domain-specific system prompts for intelligence analysts. |
| Export | `arkham_shard_ach/export.py` | Multi-format export (JSON, CSV, PDF, Markdown) implementation. |

## CORE LOGIC
- **Disconfirming Evidence**: The primary scoring metric is the **inconsistency count**. Unlike traditional weighted averages, hypotheses with the fewest contradictions (`-` and `--`) are ranked highest.
- **Scoring Algorithm**: `ACHScorer` calculates weighted consistency scores (0-100) normalized by evidence credibility (0.0-1.0), source relevance, and analyst confidence.
- **Diagnosticity Analysis**: Variance-based identification of evidence that most effectively differentiates between hypotheses. High variance ratings across hypotheses indicate high diagnosticity.
- **AI Junior Analyst Integration**:
    - **Devil's Advocate**: Forces a counter-bias mode that searches for the strongest arguments against the leading hypothesis.
    - **Premortem Analysis**: A "failure mode" analysis that assumes a hypothesis is wrong and works backwards to identify early warning indicators.
    - **Cone of Plausibility**: Generates branching scenario trees with probability assignments and trigger conditions for prospective analysis.
- **Evidence Extraction**: Automatically extracts relevant claims from document text using LLM classification, mapping them to structured `Evidence` objects.

## INTEGRATION
- **Manifest (v5)**: Defined in `shard.yaml`. It manages navigation sub-routes (Matrices, Scenarios, New Analysis) and declares dependencies on `database`, `events`, `llm`, and `vectors`.
- **Frame Services**:
    - **LLMService**: Powers all AI-assisted analytical tasks and Junior Analyst streaming features.
    - **VectorService**: Enables corpus-wide evidence search using pgvector similarity.
    - **EventBus**: Subscribes to `document.processed` to link new evidence and publishes `ach.analysis.completed` for project-wide reporting.
- **State Strategy**: Uses `url` state strategy for `matrixId`, `hypothesisId`, and `tab` selection to ensure shareable analysis views.
- **UI Shell**: Custom React pages at `/ach` provide a high-performance grid interface for N-by-M matrix manipulation, bypassing the generic list-view fallbacks.
- **Data Schema**: Operates within the isolated `arkham_ach` PostgreSQL schema, managing its own migrations during shard initialization.
