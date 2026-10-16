ALTER TABLE career.job_resume_matches
    ADD CONSTRAINT job_resume_matches_user_id_id_key
    UNIQUE (user_id, id);

ALTER TABLE career.tailored_resume_drafts
    ADD CONSTRAINT tailored_resume_drafts_user_id_id_key
        UNIQUE (user_id, id),
    ADD COLUMN snapshot_id TEXT;

UPDATE career.tailored_resume_drafts AS draft
SET snapshot_id = draft.data->>'snapshot_id'
WHERE draft.snapshot_id IS NULL
  AND draft.data ? 'snapshot_id'
  AND EXISTS (
      SELECT 1
      FROM career.job_resume_matches AS match
      WHERE match.user_id = draft.user_id
        AND match.id = draft.data->>'snapshot_id'
  );

ALTER TABLE career.tailored_resume_drafts
    ADD CONSTRAINT tailored_resume_drafts_user_snapshot_fkey
        FOREIGN KEY (user_id, snapshot_id)
        REFERENCES career.job_resume_matches(user_id, id);

CREATE TABLE career.tailored_resume_exports (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    draft_id TEXT NOT NULL,
    draft_version INTEGER NOT NULL CHECK (draft_version >= 1),
    docx_blob_id UUID NOT NULL,
    pdf_blob_id UUID NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, draft_id, draft_version),
    FOREIGN KEY (user_id, draft_id)
        REFERENCES career.tailored_resume_drafts(user_id, id),
    FOREIGN KEY (user_id, docx_blob_id)
        REFERENCES blob.objects(user_id, id),
    FOREIGN KEY (user_id, pdf_blob_id)
        REFERENCES blob.objects(user_id, id)
);

ALTER TABLE career.tailored_resume_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE career.tailored_resume_exports FORCE ROW LEVEL SECURITY;

CREATE POLICY user_isolation ON career.tailored_resume_exports
    USING (user_id = current_setting('app.user_id', true))
    WITH CHECK (user_id = current_setting('app.user_id', true));
