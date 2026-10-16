CREATE TEMP TABLE legacy_blob_candidates ON COMMIT DROP AS
SELECT packet.blob_id AS id, packet.user_id, 'application_packet' AS kind
FROM career.application_packets AS packet
WHERE packet.blob_id IS NOT NULL
UNION
SELECT export.docx_blob_id, export.user_id, 'tailored_resume_docx'
FROM career.tailored_resume_exports AS export
UNION
SELECT export.pdf_blob_id, export.user_id, 'tailored_resume_pdf'
FROM career.tailored_resume_exports AS export;

UPDATE career.interview_sessions
SET data = data - 'snapshot_id' - 'legacy_snapshot_id'
WHERE data ? 'snapshot_id' OR data ? 'legacy_snapshot_id';

DROP TRIGGER IF EXISTS tailored_resume_drafts_visible_job
ON career.tailored_resume_drafts;
DROP TRIGGER IF EXISTS application_packets_visible_job
ON career.application_packets;
DROP TRIGGER IF EXISTS job_resume_matches_visible_job
ON career.job_resume_matches;

DROP TABLE career.tailored_resume_exports;
DROP TABLE career.tailored_resume_drafts;
DROP TABLE career.application_packets;
DROP TABLE career.job_resume_matches;

DELETE FROM blob.objects AS blob
USING legacy_blob_candidates AS candidate
WHERE blob.id = candidate.id
  AND blob.user_id = candidate.user_id
  AND blob.scope = 'user'
  AND blob.kind = candidate.kind
  AND blob.kind IN (
      'application_packet',
      'tailored_resume_docx',
      'tailored_resume_pdf'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM career.resume_imports AS resume
      WHERE resume.blob_id = blob.id
  )
  AND NOT EXISTS (
      SELECT 1
      FROM catalog.raw_snapshots AS snapshot
      WHERE snapshot.blob_id = blob.id
  );
