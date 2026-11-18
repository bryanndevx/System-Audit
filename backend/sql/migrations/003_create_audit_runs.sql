-- Ejecutar exclusivamente en la base interna, después de 001 y 002.
CREATE TABLE IF NOT EXISTS public.audit_runs (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users(id),
    database_name VARCHAR(63) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    result JSONB NOT NULL,
    CONSTRAINT audit_runs_result_object CHECK (jsonb_typeof(result) = 'object'),
    CONSTRAINT audit_runs_result_activities CHECK (
        result ? 'actividades' AND jsonb_typeof(result -> 'actividades') = 'array'
    )
);

CREATE INDEX IF NOT EXISTS audit_runs_user_date_idx
    ON public.audit_runs (user_id, created_at DESC, id DESC);
