CREATE SCHEMA IF NOT EXISTS runtime;

CREATE TABLE IF NOT EXISTS runtime.conversations (
    conversation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    summary_version INTEGER NOT NULL DEFAULT 0 CHECK (summary_version >= 0),
    summary_text TEXT,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runtime.attribution_cases (
    case_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES runtime.conversations(conversation_id),
    subject_id TEXT NOT NULL,
    scenario_code TEXT,
    question_text TEXT NOT NULL CHECK (char_length(question_text) BETWEEN 5 AND 2000),
    input_fingerprint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'created', 'validating', 'planning', 'executing', 'synthesizing',
        'completed', 'needs_input', 'failed', 'cancelling', 'cancelled', 'rejected'
    )),
    cancel_requested_at TIMESTAMPTZ,
    cancel_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (subject_id, conversation_id, input_fingerprint, idempotency_key)
);

CREATE TABLE IF NOT EXISTS runtime.case_state_transitions (
    transition_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES runtime.attribution_cases(case_id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    reason_code TEXT,
    actor_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runtime.analysis_plans (
    plan_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES runtime.attribution_cases(case_id),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    status TEXT NOT NULL DEFAULT 'planned',
    steps_snapshot JSONB NOT NULL,
    current_step_no INTEGER NOT NULL DEFAULT 0 CHECK (current_step_no >= 0),
    max_steps INTEGER NOT NULL DEFAULT 8 CHECK (max_steps BETWEEN 1 AND 8),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superseded_at TIMESTAMPTZ,
    UNIQUE (case_id, version_no)
);

CREATE TABLE IF NOT EXISTS runtime.tool_executions (
    execution_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES runtime.attribution_cases(case_id),
    plan_id TEXT NOT NULL REFERENCES runtime.analysis_plans(plan_id),
    step_no INTEGER NOT NULL CHECK (step_no > 0),
    tool_name TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    input_summary TEXT,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'timeout')),
    attempt_no INTEGER NOT NULL DEFAULT 1 CHECK (attempt_no BETWEEN 1 AND 2),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    error_class TEXT,
    error_detail TEXT,
    UNIQUE (case_id, plan_id, step_no, tool_name, input_fingerprint, attempt_no)
);

CREATE TABLE IF NOT EXISTS runtime.evidence (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES runtime.attribution_cases(case_id),
    execution_id TEXT REFERENCES runtime.tool_executions(execution_id),
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    source_class TEXT NOT NULL CHECK (source_class IN ('FACT', 'MOCK', 'MISSING')),
    source_version_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    rule_version_id TEXT,
    content_summary TEXT NOT NULL,
    raw_locator TEXT,
    payload_digest TEXT,
    confidence DOUBLE PRECISION CHECK (confidence BETWEEN 0 AND 1),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (case_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS runtime.attribution_results (
    result_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES runtime.attribution_cases(case_id),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    status TEXT NOT NULL,
    six_part_content JSONB NOT NULL,
    key_metrics JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    manual_review_required BOOLEAN NOT NULL,
    based_on_evidence_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (case_id, version_no)
);

CREATE TABLE IF NOT EXISTS runtime.result_evidence_refs (
    result_id TEXT NOT NULL REFERENCES runtime.attribution_results(result_id),
    evidence_id TEXT NOT NULL REFERENCES runtime.evidence(evidence_id),
    citation_order INTEGER NOT NULL CHECK (citation_order > 0),
    usage_type TEXT NOT NULL,
    claim_fragment TEXT,
    PRIMARY KEY (result_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS attribution_cases_conversation_created_idx
    ON runtime.attribution_cases (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS case_state_transitions_case_occurred_idx
    ON runtime.case_state_transitions (case_id, occurred_at);
CREATE INDEX IF NOT EXISTS tool_executions_case_started_idx
    ON runtime.tool_executions (case_id, started_at);
CREATE INDEX IF NOT EXISTS evidence_case_sequence_idx
    ON runtime.evidence (case_id, sequence_no);
CREATE INDEX IF NOT EXISTS attribution_results_case_version_idx
    ON runtime.attribution_results (case_id, version_no);
