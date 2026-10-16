# Resume Import And Career Vault Design

## Goal

Add the first Stage 9 / P1 capability: import one user's resume from pasted
text, PDF, or DOCX; produce a structured preview; confirm facts section by
section; and persist only confirmed facts in a local Career Vault.

This stage does not implement job matching, resume rewriting, application
packets, or automatic submission.

## Product Decisions

- The product manages one candidate master profile.
- Input formats are pasted text, text-based PDF, and DOCX.
- Confirmation is section based:
  `basic`, `education`, `experience`, `project`, and `skill`.
- Original inputs remain on the local machine with a database reference.
- Sensitive fields are stored locally but masked by default.
- A new import never silently overwrites confirmed facts.
- The user explicitly chose to begin P1 before the original seven-day stability
  observation gate completed.

## Architecture

The implementation keeps four responsibilities separate:

```text
GUI local upload
  -> authenticated OpenWorker staging endpoint
  -> local deterministic text extraction
  -> opaque upload token

Career Agent
  -> get_resume_import_text(upload token)
  -> semantic extraction through the existing Provider Router
  -> preview_resume_import(structured proposal)

Career MCP
  -> schema and consistency validation
  -> staged structured preview
  -> confirm_resume_sections
  -> Career Vault
```

The staging endpoint only stores a private file and extracts text. It does not
understand candidate facts or write the Career Vault. Resume domain behavior
remains in `extensions/career_mcp`.

Career MCP never creates a model client. Semantic extraction is performed by
the current Career Agent through OpenWorker's existing Provider Router.

## Private Storage

Private files live under the configured OpenWorker state directory:

```text
.local-state/career-private/
├── resumes/
│   └── <sha256>.<pdf|docx|txt>
└── staged/
    └── <upload-token>.json
```

Requirements:

- The directory is ignored by Git.
- Paths stored in SQLite are relative to `career-private`.
- Upload tokens use cryptographically random values and expire after 24 hours.
- Re-uploading identical bytes reuses the content-addressed original.
- A staged record stores extracted text locally, but full text is never written
  to normal application logs or returned in generic error messages.
- The staging endpoint requires the normal local OpenWorker token.

## Input Limits And Extraction

### Pasted text

- UTF-8 text only.
- Minimum 20 non-whitespace characters.
- Maximum 200,000 characters.

### PDF

- Maximum 10 MB and 20 pages.
- Reuse local `pypdf` extraction.
- Reject encrypted, damaged, or text-empty/scanned PDFs.
- OCR is explicitly out of scope.

### DOCX

- Maximum 10 MB.
- Add `python-docx` to the Career MCP package.
- Extract paragraphs and table cell text in document order.
- Reject damaged ZIP/XML packages.
- Do not execute macros, external links, or embedded objects.
- `.doc`, `.docm`, RTF, images, and archives are out of scope.

All formats normalize newlines and Unicode whitespace without changing factual
content.

## Data Model

Schema v4 adds:

### `resume_imports`

```text
id
content_hash UNIQUE
upload_token UNIQUE
source_kind          text | pdf | docx
original_filename
private_path
extracted_text
status               staged | previewed | partially_confirmed | confirmed | discarded
expires_at
created_at
updated_at
```

`extracted_text` remains local in SQLite to make previews reproducible. It is
never included in list APIs or logs.

### `candidate_profile`

Exactly one row:

```text
id
display_name
current_version
created_at
updated_at
```

### `candidate_facts`

```text
id
profile_id
section              basic | education | experience | project | skill
fact_key
fact_value_json
sensitivity          public | personal | sensitive
source_import_id
confirmed_at
created_at
updated_at
```

Facts are replaced atomically by confirmed section, not field by field. This
prevents a partial edit from mixing two versions of one experience section.

### `profile_versions`

```text
id
profile_id
version_number
confirmed_sections_json
snapshot_json
source_import_id
created_at
UNIQUE(profile_id, version_number)
```

Every confirmation creates one immutable snapshot. A partial confirmation
increments the profile version and leaves unconfirmed sections unchanged.

### `resume_previews`

```text
id
resume_import_id
preview_token UNIQUE
proposal_json
conflicts_json
confirmed_sections_json
expires_at
created_at
updated_at
```

Previews expire after 24 hours but remain locally auditable until discarded or
deleted with the candidate profile.

## Structured Resume Contract

The Agent submits this shape:

```json
{
  "basic": {
    "name": "张三",
    "phone": "13800000000",
    "email": "name@example.com",
    "location": "北京",
    "summary": "..."
  },
  "education": [
    {
      "school": "...",
      "degree": "...",
      "major": "...",
      "start_date": "2022-09",
      "end_date": "2026-06",
      "details": ["..."]
    }
  ],
  "experience": [
    {
      "organization": "...",
      "title": "...",
      "start_date": "2025-01",
      "end_date": "2025-06",
      "location": "...",
      "highlights": ["..."]
    }
  ],
  "project": [
    {
      "name": "...",
      "role": "...",
      "start_date": null,
      "end_date": null,
      "highlights": ["..."],
      "technologies": ["..."]
    }
  ],
  "skill": [
    {
      "name": "Python",
      "level": null,
      "evidence": null
    }
  ],
  "missing_fields": [],
  "warnings": []
}
```

Rules:

- Empty sections use an empty object or list, not fabricated placeholders.
- Dates accept `YYYY`, `YYYY-MM`, or null.
- `end_date` may be the literal `present`.
- Highlights preserve claims from the source; the Agent must not add metrics.
- Skill levels and evidence remain null unless explicitly present.
- Unknown fields are rejected.
- Strings and list sizes have bounded lengths.

## Interfaces

### Local upload endpoint

```text
POST /v1/career/resumes/stage
```

Input:

```json
{
  "filename": "resume.pdf",
  "mime": "application/pdf",
  "data_base64": "..."
}
```

For pasted text:

```json
{
  "filename": "pasted-resume.txt",
  "mime": "text/plain",
  "text": "..."
}
```

Success returns only:

```json
{
  "ok": true,
  "upload_token": "...",
  "source_kind": "pdf",
  "filename": "resume.pdf",
  "sha256": "...",
  "characters": 8421,
  "expires_at": "..."
}
```

The endpoint delegates extraction and private storage to the Career resume
service through a small extension boundary. It does not import Career MCP into
generic OpenWorker modules at import time.

### Career MCP tools

#### `get_resume_import_text(upload_token)`

Returns extracted text and metadata after validating the token. This is the
explicit point where private resume text enters the current model context.

#### `preview_resume_import(upload_token, proposal)`

Validates the structured proposal, compares it with confirmed facts, and
returns:

- `preview_token`;
- normalized five-section proposal;
- missing fields and warnings;
- section-level conflicts with the current profile;
- masked sensitive fields.

It does not update the candidate profile.

#### `confirm_resume_sections(preview_token, sections, corrections)`

Write-risk tool. `sections` must be a non-empty subset of the five allowed
sections. `corrections` uses the same section schema and replaces the proposed
value for selected sections before validation.

The tool:

1. rejects expired or discarded previews;
2. validates all selected sections;
3. atomically replaces facts for selected sections;
4. creates one immutable profile version;
5. records confirmed sections on the preview;
6. marks the import `confirmed` only when all five sections are confirmed,
   otherwise `partially_confirmed`.

#### `get_candidate_profile(include_sensitive=false)`

Returns confirmed facts only. By default:

- name is partially masked;
- phone keeps only the final four digits;
- email masks the local part;
- detailed address is replaced by city-level location when available.

`include_sensitive=true` returns local clear text and remains an approval-gated
read because it places private information into model context.

#### `discard_resume_import(preview_token)`

Deletes an unconfirmed staged preview and its original only when no confirmed
profile version references the import.

#### `delete_candidate_profile(confirm_text)`

Requires the exact confirmation phrase `DELETE MY CAREER PROFILE`. It deletes
the master profile, facts, versions, previews, imports, and private originals.
The response returns counts only.

## GUI Flow

Add a minimal Resume Import action to the Career start/session surface:

1. choose PDF or DOCX, or paste text;
2. upload and show filename, size/characters, hash prefix, and expiry;
3. send a prepared Career prompt containing only the upload token and explicit
   instructions to load the resume import Skill;
4. render the Agent's five-section preview in the conversation;
5. user confirms or corrects sections through normal conversation;
6. write operations continue through OpenWorker approval cards.

No standalone resume dashboard is added in this stage.

## Skill Behavior

Create `.coworker/skills/career-resume-import/SKILL.md`.

The Skill must:

- explain when private text is sent to the model;
- call `get_resume_import_text` before extraction;
- preserve source claims exactly;
- call `preview_resume_import` before any confirmation;
- ask for section-level confirmation;
- never call `confirm_resume_sections` without explicit user confirmation;
- use only confirmed facts for application material;
- mask sensitive fields in ordinary summaries;
- report extraction and schema errors directly.

Update `career-application-packet` to require
`get_candidate_profile()` and reject unconfirmed preview data.

## Conflict And Version Rules

- Re-importing identical content returns the existing import and a new or
  reusable preview token without duplicating originals.
- A proposed section identical to current confirmed facts reports no conflict.
- A different non-empty section reports a conflict with masked current and
  proposed summaries.
- Confirmation of a conflicting section is an explicit replacement.
- Unselected sections remain unchanged.
- Empty proposed sections never erase confirmed sections unless selected and
  explicitly confirmed as empty.

## Error Handling

Stable codes:

```text
INVALID_INPUT
UNSUPPORTED_FORMAT
FILE_TOO_LARGE
PDF_PAGE_LIMIT
NO_EXTRACTABLE_TEXT
UPLOAD_NOT_FOUND
UPLOAD_EXPIRED
PREVIEW_NOT_FOUND
PREVIEW_EXPIRED
PROFILE_NOT_FOUND
CONFIRMATION_REQUIRED
PERSISTENCE_ERROR
```

Errors never include extracted resume text, raw phone numbers, email addresses,
or private paths.

## Security And Privacy

- Localhost API token is required.
- Filenames are sanitized and never used as storage paths.
- DOCX ZIP members are never extracted to disk.
- Parser input is bounded before parsing.
- Logs contain token prefixes, hashes, sizes, statuses, and durations only.
- Resume data is not included in crawler backups or public artifacts.
- Nothing is used for training or sharing.
- External sending and application submission remain out of scope.

## Testing

Offline fixtures use synthetic candidate data.

Required tests:

- text, PDF, and DOCX extraction produce equivalent normalized text;
- encrypted/scanned PDF and damaged DOCX fail safely;
- size/page/character limits are enforced;
- duplicate bytes reuse the original;
- expired tokens cannot expose text;
- preview schema rejects unknown fields and invalid dates;
- preview does not change confirmed facts;
- five sections can be confirmed independently;
- correction values replace proposals before confirmation;
- conflicts never auto-overwrite;
- profile versions are immutable and monotonic;
- default profile response masks sensitive fields;
- clear-text sensitive reads require the explicit path;
- discard and full deletion remove allowed files and rows;
- errors and logs contain no synthetic full resume text;
- GUI upload supports PDF, DOCX, and pasted text;
- real smoke completes upload, preview, one section confirmation, masked query,
  and cleanup without using a real user resume.

## Acceptance

The stage is complete when:

- one synthetic text, PDF, and DOCX resume each reach the same five-section
  preview;
- no profile facts exist before confirmation;
- selected sections become confirmed and versioned;
- unselected sections remain absent or unchanged;
- ordinary profile reads are masked;
- original files are local, referenced, and deletable;
- full backend and GUI regressions pass;
- Server and GUI remain healthy on model
  `ep-20260806151220-8km7l`.
