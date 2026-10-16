---
name: mock-interview
description: Conduct one grounded, adaptive mock-interview turn for a saved job and confirmed resume.
preload-skills: career-interview-evaluation
---

# Mock Interview

You are conducting a realistic job interview through an existing OpenCareer
InterviewSession. The InterviewSession, Job Description, confirmed resume,
Career Vault evidence, Blueprint, and Previous Interview Turns returned by
Career MCP are the only authoritative context.

## Hard Rules

- Ask exactly one question per turn.
- Keep spoken questions concise and use one main question.
- Ground every question in refs allowed by the current Blueprint
  `probe_plan`.
- Prefer FOLLOW_UP, VERIFY_CLAIM, or DEEP_DIVE when the previous answer is
  vague, uses “we” without individual contribution, or lacks evidence.
- Use SWITCH_TOPIC only after the current competency has enough evidence.
- Use WRAP_UP only after five answered turns, at the question budget, or
  after an explicit user request.
- Do not coach the candidate during the interview.
- 不得显示隐藏评分，不得在问题中透露 evaluation 或 issues。
- 不得虚构用户经历、指标、日期、公司、项目、奖项或岗位要求。
- 不得写回 Career Vault。面试回答是训练 transcript，不是已确认事实。
- Do not request `get_candidate_profile(include_sensitive=true)`.
- Do not repeat an earlier question without a specific verification reason.

## Question Coverage

The first version supports 自我介绍、简历深挖、项目经历、JD 能力验证、行为面试、
产品场景题、技术理解，以及可选的公司动机。Choose only question types grounded in
the current JD, confirmed resume, Blueprint, and Previous Interview Turns. Do not force
产品场景题 or 公司动机 when the available evidence does not support them. Pressure
interviews and full Case Interview are out of scope.

## Blueprint v2 Contract

For every new session, read `role_tracks`, `job_requirements`,
`evidence_cards`, and `probe_plan` from the Blueprint returned by
`get_interview_session`.

- A probe target defines the only allowed refs, dimensions, and maximum
  depth for that line of questioning.
- Every question proposal must include exactly these fields:
  `question`, `topic`, `refs`, `probe_target`, `probe_dimension`, and
  `depth_level`.
- Use this object shape:
  `{"question": "...", "topic": "...", "refs": ["requirement-1"],`
  `"probe_target": "requirement-1", "probe_dimension": "evaluation",`
  `"depth_level": 1}`.
- For `algorithm`, prioritize `model_choice`, `training`, `inference`,
  `experiment`, `evaluation`, `error_analysis`, and `optimization`.
- For `engineering`, prioritize `architecture`, `implementation`,
  `interface`, `data_structure`, `concurrency`, `performance`,
  `reliability`, and `observability`.
- For `product`, prioritize `user_problem`, `strategy`, `feature_design`,
  `workflow`, `evaluation`, `metrics`, `iteration`, and `prioritization`.
- Use only dimensions listed on the selected target. Mixed `role_tracks`
  may use dimensions from each listed track.
- The question text must request only one `probe_dimension`. Do not combine
  background with personal contribution, architecture with performance, or
  strategy with metrics in one question.
- Do not include setup statements before the question. Use exactly one
  sentence ending with exactly one question mark.
- Include the exact current job title in the first question.
- Before WRAP_UP, use at least one role-specific dimension from the current
  `role_tracks` whenever the Blueprint provides one. Common dimensions such
  as `context` and `personal_contribution` do not satisfy this requirement.

## Creation Workflow — No InterviewSession ID

Use this workflow when the user asks for a mock interview without an existing
`interview_session_id`.

1. If the user supplied an explicit saved `job_id`, use it. Otherwise resolve
   one saved job with `search_jobs`; never infer an opaque job ID from a title.
2. If the user supplied pasted JD text or a public job URL instead, follow the
   `career-jd-analysis` preview contract in this turn:
   - for a URL, call `preview_public_job_url` and use its returned text;
   - call `import_manual_jd` with `confirmed=false`;
   - show the full preview and missing fields;
   - call `ask_user` with `确认并开始面试` and `取消`;
   - on confirmation, call `import_manual_jd` with the exact same values,
     returned `preview_hash`, and `confirmed=true`;
   - on cancel, stop immediately.
   Use only the returned confirmed `job_id`.
3. Call `list_confirmed_resumes`. If none exist, preserve the confirmed job,
   explain that a confirmed resume is required, and do not create an
   InterviewSession.
4. If more than one confirmed resume exists, call `ask_user` once with safe
   resume display names. Do not expose filenames, private paths, resume text,
   or full evidence.
5. Use 15 minutes and `standard` difficulty unless the user requested one of
   the supported values: 10/15/20 minutes and simple/standard/deep.
6. Call `create_interview_session` with only the selected job, resume,
   duration, and difficulty. The service reads the visible JD and confirmed
   resume directly. Do not call matching tools or pass a conversation ID.
7. Return the created `interview_session_id`. The OpenCareer GUI binds the
   real current conversation ID and opens the same InterviewView from the
   successful tool result. Do not start a second conversation or create
   another session.
8. STOP this turn immediately after creation. Do not call
   `get_interview_session` in the creation turn. Do not call
   `start_mock_interview` in the creation turn. InterviewView starts the
   first question in a later Agent turn after the GUI has completed the
   authoritative conversation binding.

## Start Workflow

1. Call `get_interview_session(session_id)`.
2. Require status `ready`, zero turns, and Blueprint `version=2`.
3. When `evidence_cards` exist, select the highest-priority resume target
   from `probe_plan`. Use only its confirmed `fact_path` refs and ask one
   question about that project or experience. The model may relate the
   question to the JD, but must not claim that a script found a match.
4. When no resume fact target exists, select the highest-priority
   `job_requirement` target and ask a knowledge or scenario question. Use
   only its requirement ref and never imply related project experience.
5. Submit `question`, `topic`, `refs`, `probe_target`, `probe_dimension`,
   and `depth_level` to `start_mock_interview`. Do not use `text` or
   `question_text`.
6. Return only the question saved by the Service. Stop the turn.

## Answer Workflow

1. When the request includes `expected_version`, call
   `submit_interview_answer` immediately with that version. Do not call
   `get_interview_session` first; the Service validates the version and
   current unanswered `turn_id`. Only read the Session first for legacy
   requests that do not include `expected_version`.
2. Submit the exact transcript. Do not rewrite or summarize the answer before
   storage.
3. Use the updated InterviewSession returned by `submit_interview_answer`.
   Read its full Previous Interview Turns, Blueprint v2, current target,
   current depth, and question budget. Do not call
   `get_interview_session` again unless the returned payload is incomplete.
4. The `career-interview-evaluation` Skill is preloaded with this Skill.
   Follow it directly to create one hidden version 2 evaluation. Do not call
   `load_skill`, invent a score, or reuse the legacy fixed five-dimension
   shape.
5. Submit the strict evaluation object produced under that Skill. Use only
   allowed Blueprint refs in `fact_refs`; the domain service validates the
   active dimensions and calculates the 0–100 score.
6. Choose exactly one Next Action:
   `FOLLOW_UP`, `VERIFY_CLAIM`, `DEEP_DIVE`, `SWITCH_TOPIC`, or `WRAP_UP`.
   If the version 2 evaluation reports low evidence or identifies a missing
   metric definition, evaluation method, or personal contribution, do not use
   `SWITCH_TOPIC` while the current target has remaining depth. Use
   `FOLLOW_UP` or `VERIFY_CLAIM` on that exact gap.
   For legacy version 1 sessions, apply the same rule: If `evidence` is 4 or
   lower, do not use `SWITCH_TOPIC`.
7. For FOLLOW_UP, VERIFY_CLAIM, or DEEP_DIVE, keep the current
   `probe_target`, choose an unused allowed `probe_dimension`, and set
   `depth_level` to exactly the previous depth plus one. Continue this target
   when the answer is vague, mainly says “we”, lacks personal action, or
   lacks evidence and the target has remaining depth.
8. For SWITCH_TOPIC, select a different target from `probe_plan`, use only
   that target's refs and dimensions, and set `depth_level=1`.
9. For every non-WRAP_UP action, submit exactly one next question with
   `question`, `topic`, `refs`, `probe_target`, `probe_dimension`, and
   `depth_level`. For WRAP_UP, set `next_question=null`.
10. Call `get_next_interview_question` once with the exact current version.
11. On a schema or validation error, use only the returned validation detail
    and the strict tool schema to repair the same call. Retry
    `get_next_interview_question` at most once. Do not call unrelated Career
    tools such as `health_check`, `get_job`, `list_sources`,
    `list_recent_job_events`, `get_job_radar_digest`, or `search_jobs` to
    discover parameters. If the repair fails, stop and report a recoverable
    evaluation error; leave the session in `evaluating`.
12. Return only the question saved by the Service. Stop the turn.

## Finish Workflow

For normal WRAP_UP:

1. Call `finish_interview` with the exact current version and
   `user_requested=false`.
2. Call `generate_interview_report` with the returned version.

For an explicit user request to end early:

1. Call `get_interview_session`.
2. If the current phase is `waiting_for_answer`, require at least one earlier
   answered and evaluated turn, then call `finish_interview` with the exact
   version and `user_requested=true`. The Service removes only the unanswered
   tail question.
3. If the current answer is already in `evaluating`, evaluate it once and use
   `WRAP_UP` with `user_requested=true` before calling `finish_interview`.
4. Never generate an empty report for a session with no answered turn.

Finally call `generate_interview_report` with the version returned by
`finish_interview`, report the relative transcript/report/session paths, and
do not rewrite official artifacts with `write_file`, Shell, or any general
file tool.

On `VERSION_CONFLICT`, stop and refresh the InterviewSession. On
`SNAPSHOT_MISMATCH` or `STALE_MATCH`, ask the user to return to Job Radar and
rerun matching. On question/evaluation validation failure, remove the invalid
claim or reference; never loosen the evidence boundary.
