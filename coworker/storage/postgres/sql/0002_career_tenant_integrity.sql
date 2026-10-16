ALTER TABLE career.resume_imports
    ADD CONSTRAINT resume_imports_user_id_id_key
    UNIQUE (user_id, id);

ALTER TABLE career.candidate_profiles
    ADD CONSTRAINT candidate_profiles_user_id_id_key
    UNIQUE (user_id, id);

ALTER TABLE career.candidate_facts
    DROP CONSTRAINT candidate_facts_profile_id_fkey,
    ADD CONSTRAINT candidate_facts_user_profile_fkey
        FOREIGN KEY (user_id, profile_id)
        REFERENCES career.candidate_profiles(user_id, id);

ALTER TABLE career.profile_versions
    DROP CONSTRAINT profile_versions_profile_id_fkey,
    ADD CONSTRAINT profile_versions_user_profile_fkey
        FOREIGN KEY (user_id, profile_id)
        REFERENCES career.candidate_profiles(user_id, id);

ALTER TABLE career.resume_previews
    DROP CONSTRAINT resume_previews_resume_import_id_fkey,
    ADD CONSTRAINT resume_previews_user_resume_fkey
        FOREIGN KEY (user_id, resume_import_id)
        REFERENCES career.resume_imports(user_id, id);

ALTER TABLE career.job_resume_matches
    DROP CONSTRAINT job_resume_matches_resume_import_id_fkey,
    ADD CONSTRAINT job_resume_matches_user_resume_fkey
        FOREIGN KEY (user_id, resume_import_id)
        REFERENCES career.resume_imports(user_id, id);

ALTER TABLE career.tailored_resume_drafts
    DROP CONSTRAINT tailored_resume_drafts_resume_import_id_fkey,
    ADD CONSTRAINT tailored_resume_drafts_user_resume_fkey
        FOREIGN KEY (user_id, resume_import_id)
        REFERENCES career.resume_imports(user_id, id);

ALTER TABLE career.interview_sessions
    ADD CONSTRAINT interview_sessions_user_id_id_key
        UNIQUE (user_id, id),
    DROP CONSTRAINT interview_sessions_resume_import_id_fkey,
    ADD CONSTRAINT interview_sessions_user_resume_fkey
        FOREIGN KEY (user_id, resume_import_id)
        REFERENCES career.resume_imports(user_id, id);

ALTER TABLE career.interview_turns
    DROP CONSTRAINT interview_turns_session_id_fkey,
    ADD CONSTRAINT interview_turns_user_session_fkey
        FOREIGN KEY (user_id, session_id)
        REFERENCES career.interview_sessions(user_id, id);

CREATE UNIQUE INDEX interview_sessions_one_active
    ON career.interview_sessions(user_id, job_id, resume_import_id)
    WHERE data->>'status' IN ('ready', 'in_progress');
