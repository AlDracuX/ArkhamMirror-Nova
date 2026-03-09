# Future Shard Specifications

Brainstormed shard concepts for the ArkhamMirror-Nova fork. Organized by category, ranked by litigation impact.

**Existing shards (30):** dashboard, settings, ingest, documents, parse, embed, ocr, search, ach, anomalies, claims, contradictions, credibility, entities, patterns, provenance, graph, timeline, export, reports, letters, packets, templates, summary, projects, casemap, deadlines, witnesses, media-forensics, shell

---

## Category: Litigation Warfare (Direct Case Impact)

### 1. cross-exam — Cross-Examination Engine

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 39 |
| **Icon** | Swords |
| **Complements** | witnesses, contradictions, claims, credibility |
| **LLM Required** | Yes |

**Description:** Generates cross-examination question trees by analyzing witness statements against documentary evidence, flagging internal inconsistencies and conflicts with other witnesses. Scores each question by "damage potential" — how much the answer, regardless of direction, undermines the respondent's case. Auto-generates impeachment sequences when witness statements conflict with dated documents.

**Capabilities:**
- Question tree generation from witness statements
- Impeachment sequence detection (statement vs document conflicts)
- Damage potential scoring per question
- Cross-reference across multiple witnesses for inconsistency chains

**Events:**
- Publishes: `crossexam.question_tree.generated`, `crossexam.impeachment.found`
- Subscribes: `witnesses.statement.created`, `contradictions.detected`, `claims.verified`

**Database Schema:**
```
arkham_crossexam.question_trees
arkham_crossexam.impeachment_sequences
arkham_crossexam.damage_scores
```

---

### 2. disclosure — Disclosure Tracker & Gap Analyzer

| Field | Value |
|-------|-------|
| **Category** | Litigation |
| **Navigation Order** | 16 |
| **Icon** | FileSearch |
| **Complements** | documents, ingest, entities, timeline |
| **LLM Required** | Optional |

**Description:** Tracks disclosure requests and responses across all 17 respondents, mapping what was requested vs. what was provided vs. what's missing. Automatically detects evasive disclosure (partial responses, redaction patterns, delayed compliance) and generates tribunal applications for specific disclosure. Scores each respondent's disclosure compliance percentage.

**Capabilities:**
- Request/response tracking per respondent
- Gap detection (requested but not provided)
- Evasion scoring (partial, redacted, delayed)
- Auto-generate specific disclosure applications
- Compliance percentage dashboard

**Events:**
- Publishes: `disclosure.gap.detected`, `disclosure.evasion.scored`, `disclosure.application.drafted`
- Subscribes: `ingest.document.processed`, `entities.extracted`

**Database Schema:**
```
arkham_disclosure.requests
arkham_disclosure.responses
arkham_disclosure.gaps
arkham_disclosure.evasion_scores
```

---

### 3. burden-map — Burden of Proof Mapper

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 32 |
| **Icon** | Scale |
| **Complements** | casemap, claims, credibility |
| **LLM Required** | Optional |

**Description:** Visual matrix mapping each legal claim to its elements, the burden holder (claimant vs respondent — critical because in discrimination claims the burden shifts), and the current evidence weight on each side. Traffic-light system: green (burden met), amber (borderline), red (gap). Automatically recalculates when new evidence is ingested.

**Capabilities:**
- Claim-to-element decomposition with burden assignment
- Reverse burden tracking (s.136 Equality Act burden shift)
- Traffic-light evidence weight visualization
- Auto-recalculation on new evidence ingestion
- Gap identification for each element

**Events:**
- Publishes: `burden.element.satisfied`, `burden.gap.critical`
- Subscribes: `casemap.theory.updated`, `claims.status.changed`, `credibility.score.updated`

**Database Schema:**
```
arkham_burden.claim_elements
arkham_burden.evidence_weights
arkham_burden.burden_assignments
```

---

### 4. skeleton — Legal Argument Builder

| Field | Value |
|-------|-------|
| **Category** | Export |
| **Navigation Order** | 52 |
| **Icon** | Scale |
| **Complements** | casemap, claims, templates, letters |
| **LLM Required** | Yes |

**Description:** Structures skeleton arguments and legal submissions in ET-compliant format. Builds argument trees from claim → legal test → evidence → authority, with automatic citation formatting. Maintains a reusable library of legal principles and case law references. Generates both full submissions and bullet-point skeletons for oral hearings.

**Capabilities:**
- Argument tree structuring (claim → test → evidence → authority)
- ET-compliant formatting (headers, paragraph numbering, citation style)
- Case law library with ratio decidendi extraction
- Full submission and bullet-point skeleton generation
- Cross-reference to bundle page numbers

**Events:**
- Publishes: `skeleton.argument.structured`, `skeleton.submission.generated`
- Subscribes: `casemap.theory.updated`, `claims.verified`

**Database Schema:**
```
arkham_skeleton.argument_trees
arkham_skeleton.authorities
arkham_skeleton.submissions
```

---

### 5. respondent-intel — Respondent Intelligence Profiles

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 40 |
| **Icon** | UserSearch |
| **Complements** | entities, graph, witnesses |
| **LLM Required** | Optional |

**Description:** Builds comprehensive profiles for each of the 17 respondents — corporate structure, key personnel, public filings, news mentions, LinkedIn history, Companies House data. Tracks relationships between respondents (who worked together, reporting lines, communication patterns). Identifies vulnerabilities: inconsistent public statements, regulatory actions, prior tribunal history.

**Capabilities:**
- Corporate structure mapping (Companies House integration)
- Personnel history and reporting line reconstruction
- Public statement tracking and inconsistency detection
- Prior litigation/tribunal history search
- Relationship graph between respondents

**Events:**
- Publishes: `respondent.profile.updated`, `respondent.connection.discovered`
- Subscribes: `entities.extracted`, `ingest.document.processed`

**Database Schema:**
```
arkham_respondent_intel.profiles
arkham_respondent_intel.connections
arkham_respondent_intel.public_records
arkham_respondent_intel.vulnerabilities
```

---

## Category: Evidence Intelligence

### 6. redline — Document Comparison & Redlining

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 35 |
| **Icon** | FileDiff |
| **Complements** | documents, parse, contradictions |
| **LLM Required** | Optional |

**Description:** Side-by-side diff of document versions with semantic comparison — catches when respondents submit "updated" versions that silently alter key passages. Tracks document lineages (draft → final → disclosed version). Generates redline reports suitable for tribunal bundles showing exactly what changed between versions.

**Capabilities:**
- Character-level and semantic diff between document versions
- Silent edit detection (changes without disclosure)
- Document lineage tracking (version chains)
- Redline report generation for tribunal bundles
- Highlight significance scoring for each change

**Events:**
- Publishes: `redline.change.detected`, `redline.silent_edit.flagged`
- Subscribes: `documents.processed`, `parse.completed`

**Database Schema:**
```
arkham_redline.comparisons
arkham_redline.version_chains
arkham_redline.changes
```

---

### 7. chain — Evidence Chain of Custody

| Field | Value |
|-------|-------|
| **Category** | Data |
| **Navigation Order** | 12 |
| **Icon** | Link |
| **Complements** | documents, provenance, ingest, media-forensics |
| **LLM Required** | No |

**Description:** Cryptographic chain-of-custody logging for every piece of evidence — when it was received, from whom, how it was stored, every access and transformation. Generates court-admissible provenance reports. Detects if files have been modified after initial ingestion. Essential for maintaining evidence integrity against challenges.

**Capabilities:**
- SHA-256 hash logging at every custody transition
- Timestamped access and transformation logging
- Court-admissible provenance report generation
- Tamper detection via hash comparison
- Import/export custody records for disclosure

**Events:**
- Publishes: `chain.evidence.logged`, `chain.integrity.verified`, `chain.tamper.detected`
- Subscribes: `ingest.document.processed`, `documents.accessed`

**Database Schema:**
```
arkham_chain.custody_events
arkham_chain.hashes
arkham_chain.provenance_reports
```

---

### 8. comms — Communication Thread Analyzer

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 36 |
| **Icon** | MessageSquare |
| **Complements** | entities, timeline, contradictions, patterns |
| **LLM Required** | Yes |

**Description:** Reconstructs email/message threads across multiple sources (BYLOR emails, disclosed documents), building conversation maps. Identifies who-knew-what-when — crucial for discrimination claims. Detects gaps in communication chains (missing replies, conspicuous silences). Highlights BCC patterns and forwarding chains that reveal hidden coordination.

**Capabilities:**
- Email thread reconstruction from fragmented sources
- Who-knew-what-when timeline generation
- Missing reply / conspicuous silence detection
- BCC and forwarding chain analysis
- Hidden coordination pattern detection

**Events:**
- Publishes: `comms.thread.reconstructed`, `comms.gap.detected`, `comms.coordination.flagged`
- Subscribes: `ingest.document.processed`, `entities.extracted`

**Database Schema:**
```
arkham_comms.threads
arkham_comms.participants
arkham_comms.gaps
arkham_comms.coordination_flags
```

---

### 9. sentiment — Document Sentiment & Tone Analyzer

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 37 |
| **Icon** | HeartPulse |
| **Complements** | documents, claims, credibility, witnesses |
| **LLM Required** | Yes |

**Description:** LLM-powered analysis of tone, sentiment, and language patterns in workplace communications. Detects hostility escalation, gaslighting patterns, passive-aggressive language, and tone shifts that correlate with discriminatory intent. Compares language used toward the claimant vs. comparators. Generates "tone timeline" showing how communications shifted over time.

**Capabilities:**
- Hostility escalation detection across time
- Gaslighting and passive-aggressive pattern recognition
- Comparator language divergence analysis
- Tone timeline visualization
- Discriminatory intent signal extraction

**Events:**
- Publishes: `sentiment.hostile.detected`, `sentiment.pattern.identified`, `sentiment.comparator.divergence`
- Subscribes: `documents.processed`, `comms.thread.reconstructed`

**Database Schema:**
```
arkham_sentiment.analyses
arkham_sentiment.tone_scores
arkham_sentiment.patterns
arkham_sentiment.comparator_diffs
```

---

## Category: Strategic & Procedural

### 10. playbook — Litigation Strategy Planner

| Field | Value |
|-------|-------|
| **Category** | System |
| **Navigation Order** | 14 |
| **Icon** | Target |
| **Complements** | casemap, deadlines, burden-map, skeleton |
| **LLM Required** | Yes |

**Description:** Campaign-level litigation planning — maps the overall strategy tree (main claims, fallback positions, settlement leverage points). Models scenarios: "If claim X fails, what happens to claims Y and Z?" War-gaming tool that simulates respondent counter-arguments and plans responses. Tracks which strategic objectives each piece of evidence serves.

**Capabilities:**
- Strategy tree with main claims and fallback positions
- Scenario modeling (claim dependency chains)
- Respondent counter-argument simulation
- Evidence-to-objective mapping
- Settlement leverage analysis

**Events:**
- Publishes: `playbook.scenario.modeled`, `playbook.strategy.updated`
- Subscribes: `casemap.theory.updated`, `burden.gap.critical`, `deadlines.approaching`

**Database Schema:**
```
arkham_playbook.strategies
arkham_playbook.scenarios
arkham_playbook.evidence_objectives
```

---

### 11. rules — Procedural Rules Engine

| Field | Value |
|-------|-------|
| **Category** | System |
| **Navigation Order** | 17 |
| **Icon** | BookOpen |
| **Complements** | deadlines, templates, letters |
| **LLM Required** | No |

**Description:** Encodes Employment Tribunal Rules of Procedure, Practice Directions, and key case management principles. Auto-calculates deadlines from trigger events (e.g., "14 days from date of order"). Validates submissions for procedural compliance before filing. Flags when respondents breach procedural rules, generating applications to strike out or for unless orders.

**Capabilities:**
- ET Rules of Procedure encoded as structured data
- Deadline auto-calculation from trigger events
- Submission compliance validation
- Respondent breach detection and logging
- Auto-generate strike-out / unless order applications

**Events:**
- Publishes: `rules.deadline.calculated`, `rules.breach.detected`, `rules.compliance.checked`
- Subscribes: `deadlines.created`, `documents.processed`

**Database Schema:**
```
arkham_rules.rules
arkham_rules.calculations
arkham_rules.breaches
arkham_rules.compliance_checks
```

---

### 12. costs — Costs & Wasted Costs Tracker

| Field | Value |
|-------|-------|
| **Category** | Litigation |
| **Navigation Order** | 18 |
| **Icon** | PoundSterling |
| **Complements** | deadlines, disclosure, timeline |
| **LLM Required** | No |

**Description:** Tracks time spent, expenses, and respondent conduct for potential costs applications. In ET, costs are exceptional — but unreasonable conduct triggers them. Logs every instance of respondent delay, evasion, or vexatious behavior with dated evidence. Auto-generates Schedule of Costs and costs applications citing specific conduct instances.

**Capabilities:**
- Time and expense tracking per activity
- Respondent conduct logging (delay, evasion, vexatious behavior)
- Schedule of Costs generation
- Costs application drafting with conduct citations
- Rule 76 threshold analysis

**Events:**
- Publishes: `costs.conduct.logged`, `costs.application.ready`
- Subscribes: `disclosure.evasion.scored`, `rules.breach.detected`, `deadlines.breach.detected`

**Database Schema:**
```
arkham_costs.time_entries
arkham_costs.expenses
arkham_costs.conduct_log
arkham_costs.applications
```

---

## Category: AI-Powered

### 13. oracle — LLM Legal Research Assistant

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 41 |
| **Icon** | BookMarked |
| **Complements** | claims, casemap, skeleton, search |
| **LLM Required** | Yes |

**Description:** Semantic search across legal databases and case law, returning relevant authorities for each claim element. Distinguishes binding authority (EAT, Court of Appeal) from persuasive. Generates case summaries and extracts the ratio decidendi. Can answer natural language legal questions grounded in the case's specific facts.

**Capabilities:**
- Legal authority search (case law, statutes, regulations)
- Binding vs persuasive authority classification
- Ratio decidendi extraction and summarization
- Natural language legal Q&A grounded in case facts
- Authority chain tracking (which cases cite which)

**Events:**
- Publishes: `oracle.authority.found`, `oracle.research.completed`
- Subscribes: `casemap.theory.updated`, `claims.created`

**Database Schema:**
```
arkham_oracle.authorities
arkham_oracle.research_sessions
arkham_oracle.case_summaries
arkham_oracle.authority_chains
```

---

### 14. strategist — AI Adversarial Modeler

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 42 |
| **Icon** | Shield |
| **Complements** | playbook, witnesses, claims, respondent-intel |
| **LLM Required** | Yes |

**Description:** LLM-powered adversarial simulation — "thinks like TLT solicitors" to predict respondent arguments, likely witness testimony angles, and procedural tactics. Generates counter-argument briefings for each respondent position. Red-teams Alex's own submissions to find weaknesses before filing. Uses respondent intel to model each respondent's likely defense strategy.

**Capabilities:**
- Respondent argument prediction per claim
- Witness testimony angle simulation
- Submission red-teaming (find weaknesses before filing)
- Counter-argument briefing generation
- Tactical prediction (procedural moves, delay tactics)

**Events:**
- Publishes: `strategist.prediction.generated`, `strategist.weakness.found`
- Subscribes: `playbook.strategy.updated`, `respondent.profile.updated`, `witnesses.statement.created`

**Database Schema:**
```
arkham_strategist.predictions
arkham_strategist.counterarguments
arkham_strategist.red_team_reports
arkham_strategist.tactical_models
```

---

### 15. digest — Case Digest & Briefing Generator

| Field | Value |
|-------|-------|
| **Category** | Export |
| **Navigation Order** | 53 |
| **Icon** | Newspaper |
| **Complements** | all shards |
| **LLM Required** | Yes |

**Description:** Generates daily/weekly case digests: what changed, new evidence ingested, deadlines approaching, contradictions found, evidence gaps identified. Morning briefing format optimized for ADHD — bullet points, action items, priority ranking. Can generate situation reports for supporters/advisors who need to understand case status quickly.

**Capabilities:**
- Daily/weekly digest generation
- ADHD-optimized briefing format (bullets, actions, priorities)
- Cross-shard change aggregation
- Situation report generation for advisors
- Deadline proximity alerts with context

**Events:**
- Publishes: `digest.briefing.generated`
- Subscribes: ALL major events across shards (wildcard subscriber)

**Database Schema:**
```
arkham_digest.briefings
arkham_digest.change_log
arkham_digest.subscriptions
```

---

## Category: Data & Utility

### 16. comparator — Comparator Evidence Mapper

| Field | Value |
|-------|-------|
| **Category** | Analysis |
| **Navigation Order** | 34 |
| **Icon** | GitCompare |
| **Complements** | entities, claims, contradictions, sentiment |
| **LLM Required** | Optional |

**Description:** Specific to discrimination claims — maps how the claimant was treated vs. named comparators across every incident. Tracks parallel situations (same policy, different outcomes) and builds the "less favourable treatment" evidence matrix required for direct discrimination claims. Essential for s.13 and s.26 Equality Act arguments.

**Capabilities:**
- Claimant vs comparator treatment mapping per incident
- Parallel situation detection (same policy, different outcome)
- Less favourable treatment evidence matrix
- s.13 direct discrimination element tracking
- s.26 harassment element tracking
- Protected characteristic linkage analysis

**Events:**
- Publishes: `comparator.treatment.mapped`, `comparator.divergence.found`
- Subscribes: `entities.extracted`, `claims.created`, `documents.processed`

**Database Schema:**
```
arkham_comparator.incidents
arkham_comparator.treatments
arkham_comparator.comparators
arkham_comparator.divergences
```

---

### 17. audit-trail — System Audit & Integrity Log

| Field | Value |
|-------|-------|
| **Category** | System |
| **Navigation Order** | 95 |
| **Icon** | ScrollText |
| **Complements** | chain, all shards |
| **LLM Required** | No |

**Description:** Immutable log of every analysis, search, and modification within the platform. If respondents challenge the integrity of digital evidence or analysis methodology, this provides a complete forensic trail. Useful for demonstrating rigorous, systematic case preparation to the tribunal.

**Capabilities:**
- Immutable append-only action logging
- Full forensic trail of all platform operations
- User action audit (searches, edits, exports)
- Methodology documentation for tribunal challenges
- Export audit trail as evidence of systematic preparation

**Events:**
- Publishes: `audit.action.logged`
- Subscribes: ALL shard events (wildcard subscriber)

**Database Schema:**
```
arkham_audit.actions (append-only)
arkham_audit.sessions
arkham_audit.exports
```

---

### 18. bundle — Tribunal Bundle Builder

| Field | Value |
|-------|-------|
| **Category** | Export |
| **Navigation Order** | 55 |
| **Icon** | BookCopy |
| **Complements** | documents, export, packets, templates |
| **LLM Required** | No |

**Description:** Automates tribunal hearing bundle preparation — paginated, indexed, with agreed/disputed document markers. Follows Presidential Guidance on bundle preparation. Auto-generates the bundle index, cross-references page numbers in skeleton arguments, and produces both digital and print-ready formats. Tracks bundle versions and additions.

**Capabilities:**
- Automated pagination and indexing
- Agreed/disputed document marking
- Presidential Guidance compliance
- Bundle index auto-generation
- Page number cross-referencing in skeleton arguments
- Digital and print-ready PDF output
- Bundle versioning and additions tracking

**Events:**
- Publishes: `bundle.compiled`, `bundle.index.generated`
- Subscribes: `documents.processed`, `skeleton.submission.generated`

**Database Schema:**
```
arkham_bundle.bundles
arkham_bundle.pages
arkham_bundle.indices
arkham_bundle.versions
```

---

## Build Priority (Recommended Order)

| Priority | Shard | Rationale |
|----------|-------|-----------|
| **P0** | comparator | Directly serves the s.13/s.26 legal test — the core of the case |
| **P0** | disclosure | 17 respondents = impossible to track manually |
| **P1** | cross-exam | 10 individual respondents to cross-examine at hearing |
| **P1** | bundle | Tribunal bundle prep is mandatory and time-consuming |
| **P1** | burden-map | Visual evidence gap analysis prevents nasty surprises |
| **P2** | comms | 729 BYLOR emails need thread reconstruction |
| **P2** | skeleton | Automates the most time-intensive legal writing |
| **P2** | rules | Catches respondent procedural breaches automatically |
| **P2** | costs | Builds costs application evidence over time |
| **P3** | sentiment | Supports discrimination intent arguments |
| **P3** | redline | Catches silent document alterations |
| **P3** | chain | Evidence integrity defence |
| **P3** | strategist | Red-team submissions before filing |
| **P4** | playbook | Strategic planning aid |
| **P4** | oracle | Legal research acceleration |
| **P4** | respondent-intel | Background intelligence |
| **P4** | digest | Daily briefings |
| **P5** | audit-trail | Systematic preparation evidence |
