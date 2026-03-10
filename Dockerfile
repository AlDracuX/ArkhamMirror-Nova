# =============================================================================
# SHATTERED KANDOR: Multi-Stage Dockerfile
# Builds Frame + All Shards into a single deployable container
#
# Usage:
#   docker build -t shattered .
#   docker compose up -d
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Frontend Build (React Shell)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copy package files first for layer caching
COPY packages/arkham-shard-shell/package*.json ./

# Install dependencies (--legacy-peer-deps for react-leaflet@5 / React 18 compat)
RUN npm ci --silent --legacy-peer-deps

# Copy source and build
COPY packages/arkham-shard-shell/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Python Backend Build
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS backend-builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# Install Frame first (core dependency)
COPY packages/arkham-frame/ ./packages/arkham-frame/
RUN pip install --no-cache-dir ./packages/arkham-frame

# Install all Shards
# Copy each shard directory
COPY packages/arkham-shard-ach/ ./packages/arkham-shard-ach/
COPY packages/arkham-shard-anomalies/ ./packages/arkham-shard-anomalies/
COPY packages/arkham-shard-claims/ ./packages/arkham-shard-claims/
COPY packages/arkham-shard-contradictions/ ./packages/arkham-shard-contradictions/
COPY packages/arkham-shard-credibility/ ./packages/arkham-shard-credibility/
COPY packages/arkham-shard-dashboard/ ./packages/arkham-shard-dashboard/
COPY packages/arkham-shard-documents/ ./packages/arkham-shard-documents/
COPY packages/arkham-shard-embed/ ./packages/arkham-shard-embed/
COPY packages/arkham-shard-entities/ ./packages/arkham-shard-entities/
COPY packages/arkham-shard-export/ ./packages/arkham-shard-export/
COPY packages/arkham-shard-graph/ ./packages/arkham-shard-graph/
COPY packages/arkham-shard-ingest/ ./packages/arkham-shard-ingest/
COPY packages/arkham-shard-letters/ ./packages/arkham-shard-letters/
COPY packages/arkham-shard-ocr/ ./packages/arkham-shard-ocr/
COPY packages/arkham-shard-packets/ ./packages/arkham-shard-packets/
COPY packages/arkham-shard-parse/ ./packages/arkham-shard-parse/
COPY packages/arkham-shard-patterns/ ./packages/arkham-shard-patterns/
COPY packages/arkham-shard-projects/ ./packages/arkham-shard-projects/
COPY packages/arkham-shard-provenance/ ./packages/arkham-shard-provenance/
COPY packages/arkham-shard-reports/ ./packages/arkham-shard-reports/
COPY packages/arkham-shard-search/ ./packages/arkham-shard-search/
COPY packages/arkham-shard-settings/ ./packages/arkham-shard-settings/
COPY packages/arkham-shard-summary/ ./packages/arkham-shard-summary/
COPY packages/arkham-shard-templates/ ./packages/arkham-shard-templates/
COPY packages/arkham-shard-timeline/ ./packages/arkham-shard-timeline/
COPY packages/arkham-shard-media-forensics/ ./packages/arkham-shard-media-forensics/
COPY packages/arkham-shard-witnesses/ ./packages/arkham-shard-witnesses/
COPY packages/arkham-shard-deadlines/ ./packages/arkham-shard-deadlines/
COPY packages/arkham-shard-casemap/ ./packages/arkham-shard-casemap/

# New litigation shards (18)
COPY packages/arkham-shard-comparator/ ./packages/arkham-shard-comparator/
COPY packages/arkham-shard-disclosure/ ./packages/arkham-shard-disclosure/
COPY packages/arkham-shard-chain/ ./packages/arkham-shard-chain/
COPY packages/arkham-shard-audit-trail/ ./packages/arkham-shard-audit-trail/
COPY packages/arkham-shard-crossexam/ ./packages/arkham-shard-crossexam/
COPY packages/arkham-shard-bundle/ ./packages/arkham-shard-bundle/
COPY packages/arkham-shard-burden-map/ ./packages/arkham-shard-burden-map/
COPY packages/arkham-shard-comms/ ./packages/arkham-shard-comms/
COPY packages/arkham-shard-skeleton/ ./packages/arkham-shard-skeleton/
COPY packages/arkham-shard-rules/ ./packages/arkham-shard-rules/
COPY packages/arkham-shard-costs/ ./packages/arkham-shard-costs/
COPY packages/arkham-shard-sentiment/ ./packages/arkham-shard-sentiment/
COPY packages/arkham-shard-redline/ ./packages/arkham-shard-redline/
COPY packages/arkham-shard-strategist/ ./packages/arkham-shard-strategist/
COPY packages/arkham-shard-playbook/ ./packages/arkham-shard-playbook/
COPY packages/arkham-shard-oracle/ ./packages/arkham-shard-oracle/
COPY packages/arkham-shard-respondent-intel/ ./packages/arkham-shard-respondent-intel/
COPY packages/arkham-shard-digest/ ./packages/arkham-shard-digest/

# Install PyTorch - GPU-enabled by default for Legion (NVIDIA)
# For CPU-only: docker build --build-arg COMPUTE_BACKEND=cpu ...
ARG COMPUTE_BACKEND=cuda
ARG TORCH_INDEX_URL=""
RUN if [ "$COMPUTE_BACKEND" = "cpu" ]; then \
      pip install --no-cache-dir "torch>=2.6" --index-url https://download.pytorch.org/whl/cpu; \
    else \
      pip install --no-cache-dir "torch>=2.6" --index-url https://download.pytorch.org/whl/cu124; \
    fi

# Install each shard (continue on error for optional shards)
RUN for shard_dir in ./packages/arkham-shard-*/; do \
      if [ -f "$shard_dir/pyproject.toml" ]; then \
        echo "Installing $shard_dir..." && \
        pip install --no-cache-dir "$shard_dir" || echo "Warning: Failed to install $shard_dir"; \
      fi \
    done

# Download spaCy model for NER
RUN python -m spacy download en_core_web_sm || echo "spaCy model download skipped"

# -----------------------------------------------------------------------------
# Stage 3: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/AlDracuX/ArkhamMirror-Nova"
LABEL org.opencontainers.image.description="ArkhamMirror-Nova - Litigation Analysis Platform"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="ArkhamMirror-Nova"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    netcat-openbsd \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=backend-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy built frontend
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Copy shard manifests (needed for navigation discovery)
# Each manifest is renamed to {shard-name}.yaml to avoid overwrites
COPY packages/arkham-shard-ach/shard.yaml /app/manifests/ach.yaml
COPY packages/arkham-shard-anomalies/shard.yaml /app/manifests/anomalies.yaml
COPY packages/arkham-shard-claims/shard.yaml /app/manifests/claims.yaml
COPY packages/arkham-shard-contradictions/shard.yaml /app/manifests/contradictions.yaml
COPY packages/arkham-shard-credibility/shard.yaml /app/manifests/credibility.yaml
COPY packages/arkham-shard-dashboard/shard.yaml /app/manifests/dashboard.yaml
COPY packages/arkham-shard-documents/shard.yaml /app/manifests/documents.yaml
COPY packages/arkham-shard-embed/shard.yaml /app/manifests/embed.yaml
COPY packages/arkham-shard-entities/shard.yaml /app/manifests/entities.yaml
COPY packages/arkham-shard-export/shard.yaml /app/manifests/export.yaml
COPY packages/arkham-shard-graph/shard.yaml /app/manifests/graph.yaml
COPY packages/arkham-shard-ingest/shard.yaml /app/manifests/ingest.yaml
COPY packages/arkham-shard-letters/shard.yaml /app/manifests/letters.yaml
COPY packages/arkham-shard-ocr/shard.yaml /app/manifests/ocr.yaml
COPY packages/arkham-shard-packets/shard.yaml /app/manifests/packets.yaml
COPY packages/arkham-shard-parse/shard.yaml /app/manifests/parse.yaml
COPY packages/arkham-shard-patterns/shard.yaml /app/manifests/patterns.yaml
COPY packages/arkham-shard-projects/shard.yaml /app/manifests/projects.yaml
COPY packages/arkham-shard-provenance/shard.yaml /app/manifests/provenance.yaml
COPY packages/arkham-shard-reports/shard.yaml /app/manifests/reports.yaml
COPY packages/arkham-shard-search/shard.yaml /app/manifests/search.yaml
COPY packages/arkham-shard-settings/shard.yaml /app/manifests/settings.yaml
COPY packages/arkham-shard-summary/shard.yaml /app/manifests/summary.yaml
COPY packages/arkham-shard-templates/shard.yaml /app/manifests/templates.yaml
COPY packages/arkham-shard-timeline/shard.yaml /app/manifests/timeline.yaml
COPY packages/arkham-shard-media-forensics/shard.yaml /app/manifests/media-forensics.yaml
COPY packages/arkham-shard-witnesses/shard.yaml /app/manifests/witnesses.yaml
COPY packages/arkham-shard-deadlines/shard.yaml /app/manifests/deadlines.yaml
COPY packages/arkham-shard-casemap/shard.yaml /app/manifests/casemap.yaml
COPY packages/arkham-shard-comparator/shard.yaml /app/manifests/comparator.yaml
COPY packages/arkham-shard-disclosure/shard.yaml /app/manifests/disclosure.yaml
COPY packages/arkham-shard-chain/shard.yaml /app/manifests/chain.yaml
COPY packages/arkham-shard-audit-trail/shard.yaml /app/manifests/audit-trail.yaml
COPY packages/arkham-shard-crossexam/shard.yaml /app/manifests/crossexam.yaml
COPY packages/arkham-shard-bundle/shard.yaml /app/manifests/bundle.yaml
COPY packages/arkham-shard-burden-map/shard.yaml /app/manifests/burden-map.yaml
COPY packages/arkham-shard-comms/shard.yaml /app/manifests/comms.yaml
COPY packages/arkham-shard-skeleton/shard.yaml /app/manifests/skeleton.yaml
COPY packages/arkham-shard-rules/shard.yaml /app/manifests/rules.yaml
COPY packages/arkham-shard-costs/shard.yaml /app/manifests/costs.yaml
COPY packages/arkham-shard-sentiment/shard.yaml /app/manifests/sentiment.yaml
COPY packages/arkham-shard-redline/shard.yaml /app/manifests/redline.yaml
COPY packages/arkham-shard-strategist/shard.yaml /app/manifests/strategist.yaml
COPY packages/arkham-shard-playbook/shard.yaml /app/manifests/playbook.yaml
COPY packages/arkham-shard-oracle/shard.yaml /app/manifests/oracle.yaml
COPY packages/arkham-shard-respondent-intel/shard.yaml /app/manifests/respondent-intel.yaml
COPY packages/arkham-shard-digest/shard.yaml /app/manifests/digest.yaml

WORKDIR /app

# Create directories for data persistence
RUN mkdir -p /app/data_silo/documents \
             /app/data_silo/exports \
             /app/data_silo/temp \
             /app/data_silo/models \
             /app/config \
             /app/migrations

# Copy database migrations
COPY migrations/*.sql /app/migrations/

# Copy entrypoint script and fix line endings (Windows CRLF -> Unix LF)
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ARKHAM_SERVE_SHELL=true

# Expose API port (Shell is served from same port via static files)
EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8100/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
