\set ON_ERROR_STOP on

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TEMP TABLE cleanup_target_companies ON COMMIT DROP AS
SELECT id, slug, name
FROM catalog.companies
WHERE slug IN ('api-company', 'flow-company')
   OR slug LIKE 'packet-company-%'
   OR slug LIKE 'tailored-company-%';

CREATE TEMP TABLE cleanup_target_sources ON COMMIT DROP AS
SELECT js.id, js.company_id, js.slug, js.source_type
FROM catalog.job_sources js
JOIN cleanup_target_companies c ON c.id = js.company_id;

CREATE TEMP TABLE cleanup_target_jobs ON COMMIT DROP AS
SELECT j.id, j.company_id, j.source_id
FROM catalog.jobs j
JOIN cleanup_target_companies c ON c.id = j.company_id;

DO $cleanup$
DECLARE
    company_count INTEGER;
    source_count INTEGER;
    job_count INTEGER;
    reference_count INTEGER;
    invalid_source_count INTEGER;
    crawl_source_count INTEGER;
    active_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO company_count
    FROM cleanup_target_companies;
    SELECT COUNT(*) INTO source_count
    FROM cleanup_target_sources;
    SELECT COUNT(*) INTO job_count
    FROM cleanup_target_jobs;
    IF company_count <> 33 OR source_count <> 33 OR job_count <> 33 THEN
        RAISE EXCEPTION
            'unexpected cleanup target counts: companies=%, sources=%, jobs=%',
            company_count, source_count, job_count;
    END IF;

    SELECT COUNT(*) INTO invalid_source_count
    FROM cleanup_target_sources
    WHERE source_type NOT IN ('test', 'integration');
    IF invalid_source_count <> 0 THEN
        RAISE EXCEPTION
            'cleanup targets include % non-test sources',
            invalid_source_count;
    END IF;

    SELECT COUNT(*) INTO crawl_source_count
    FROM catalog.crawl_sources cs
    JOIN cleanup_target_companies c ON c.id = cs.company_id;
    IF crawl_source_count <> 0 THEN
        RAISE EXCEPTION
            'cleanup targets include % official crawl sources',
            crawl_source_count;
    END IF;

    SELECT COUNT(*) INTO reference_count
    FROM (
        SELECT job_id FROM career.job_tracking
        UNION ALL
        SELECT job_id FROM career.job_application_events
        UNION ALL
        SELECT job_id FROM career.application_packets
        UNION ALL
        SELECT job_id FROM career.tailored_resume_drafts
        UNION ALL
        SELECT job_id FROM career.interview_sessions
        UNION ALL
        SELECT job_id FROM career.job_resume_matches
    ) references_to_jobs
    JOIN cleanup_target_jobs target
      ON target.id = references_to_jobs.job_id;
    IF reference_count <> 0 THEN
        RAISE EXCEPTION
            'cleanup targets have % career references',
            reference_count;
    END IF;

    SELECT COUNT(*) INTO active_count
    FROM catalog.jobs
    WHERE status = 'active';
    IF active_count <> 10802 THEN
        RAISE EXCEPTION
            'unexpected active job count before cleanup: %',
            active_count;
    END IF;
END
$cleanup$;

SELECT c.slug, c.name, s.slug AS source_slug, j.id AS job_id
FROM cleanup_target_jobs j
JOIN cleanup_target_companies c ON c.id = j.company_id
JOIN cleanup_target_sources s ON s.id = j.source_id
ORDER BY c.slug, s.slug, j.id;

DELETE FROM catalog.job_events
WHERE job_id IN (SELECT id FROM cleanup_target_jobs);

DELETE FROM catalog.job_versions
WHERE job_id IN (SELECT id FROM cleanup_target_jobs);

DELETE FROM catalog.jobs
WHERE id IN (SELECT id FROM cleanup_target_jobs);

DELETE FROM catalog.job_sources
WHERE id IN (SELECT id FROM cleanup_target_sources);

DELETE FROM catalog.companies
WHERE id IN (SELECT id FROM cleanup_target_companies);

DO $cleanup$
DECLARE
    target_count INTEGER;
    active_count INTEGER;
    official_source_count INTEGER;
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO target_count
    FROM catalog.companies
    WHERE slug IN ('api-company', 'flow-company')
       OR slug LIKE 'packet-company-%'
       OR slug LIKE 'tailored-company-%';
    IF target_count <> 0 THEN
        RAISE EXCEPTION
            'test companies remain after cleanup: %',
            target_count;
    END IF;

    SELECT COUNT(*) INTO active_count
    FROM catalog.jobs
    WHERE status = 'active';
    IF active_count <> 10769 THEN
        RAISE EXCEPTION
            'unexpected active job count after cleanup: %',
            active_count;
    END IF;

    SELECT COUNT(*) INTO official_source_count
    FROM catalog.crawl_sources;
    IF official_source_count <> 34 THEN
        RAISE EXCEPTION
            'unexpected official crawl source count: %',
            official_source_count;
    END IF;

    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT crawl_source_id, external_job_id
        FROM catalog.jobs
        WHERE external_job_id IS NOT NULL
        GROUP BY crawl_source_id, external_job_id
        HAVING COUNT(*) > 1
    ) duplicates;
    IF duplicate_count <> 0 THEN
        RAISE EXCEPTION
            'duplicate catalog business keys after cleanup: %',
            duplicate_count;
    END IF;
END
$cleanup$;

COMMIT;
