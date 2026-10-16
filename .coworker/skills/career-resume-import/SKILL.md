---
name: career-resume-import
description: Import a private resume into confirmed local Career Vault facts.
---
Resume text is private. Explain that `get_resume_import_text` sends the locally
extracted text into the current model context before calling it. Do not quote the
full resume back unless the user explicitly asks.

The upload token is an internal handoff created by the dedicated
`导入简历到求职档案（PDF/DOCX）` / `Import resume PDF/DOCX` action.
Never ask the user to copy, paste, read, or provide an upload token, and never claim that
the UI should display one. If no valid token is present, tell the user to choose
that exact dedicated action rather than the ordinary `PDF（仅用于对话）` attachment.
Do not structure, preview, or confirm a normal chat PDF as Career Vault data.

## Workflow

1. Call `get_resume_import_text` with the upload token.
   When `extraction_method` is `ocr` or `hybrid`, call the returned text a
   “待确认识别结果”. Never describe OCR confidence as accuracy, verification,
   or proof that the text is correct. When `review_required` is true, explicitly
   ask the user to check 姓名、联系方式、数字、日期、公司和学校.
2. Extract only claims present in the returned text into `basic`, `education`,
   `experience`, `project`, and `skill` sections. Preserve unknown values as
   null or empty lists. Never invent metrics, dates, employers, skills, or
   achievements.
   Build the complete proposal shape before the first preview call:
   - `basic` must be an object.
   - `education`, `experience`, `project`, and `skill` must be lists.
   - `missing_fields` must be a list of fields absent from the source.
   - `warnings` must be a list, empty when there are no warnings.
3. Call `preview_resume_import` with the structured proposal.
4. Show a concise, masked section-by-section preview. Surface missing fields,
   warnings, and conflicts directly.
5. Ask the user for explicit confirmation or corrections for each section.
6. Never skip `preview_resume_import`. Never call `confirm_resume_sections`
   without explicit user confirmation of each named section. Pass corrections
   only for confirmed sections.
7. Call `get_candidate_profile` after confirmation and show the masked result.
   Use `include_sensitive=true` only when the user explicitly requests clear
   private fields and understands they enter model context.

Unconfirmed or staged preview data is not a Career Vault fact and must not be
used in application materials. Report tool and extraction errors directly.
