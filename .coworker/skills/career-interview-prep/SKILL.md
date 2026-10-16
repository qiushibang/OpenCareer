---
name: career-interview-prep
description: Build a stage-aware interview preparation pack for one saved job from the confirmed resume, then hand off to the mock interview. Invoke for 面试准备/帮我准备面试.
---

# Career Interview Prep

Prepare the user for an upcoming interview on ONE saved job. Authoritative
context: `get_job(job_id)`, one user-selected `get_confirmed_resume(resume_id)`,
plus any existing interview review artifacts for this job (fetch via the Career
interview artifact tools when present). Do not invent requirements, experience,
or metrics; unknown facts are asked, never assumed.

## Required Workflow

Ask which stage is coming (筛选轮 / 技术轮 / 主管或跨部门轮 / HR 或终面); default
to 技术轮 if unknown. Then present the pack in exactly these six sections, in
Chinese:

### 1. 可能的问题

Ordered by evidence value:

1. Points challenged or left unresolved in earlier interview reviews of this
   job — they WILL come back.
2. Gaps flagged by job-fit evaluation or resume coaching for this job.
3. Every stated JD requirement, in JD order.
4. Stage patterns only: 筛选轮 asks motivation and timeline; 技术轮 asks depth;
   主管轮 asks collaboration and ownership; HR/终面 asks values, stability,
   compensation expectations.

### 2. STAR 答案映射

Map the 3–5 most relevant resume experiences into S-T-A-R. Rule: no claim in
the room that isn't on the paper — every result told aloud must trace to a
confirmed resume line. Drafts stay drafts; they are not new Career Vault facts.

### 3. 一致性简报

List each quantified or strong claim on the resume likely to be probed, with:
the exact follow-up an interviewer would ask, the specific numbers/details the
user must have ready, and a 经不起追问 flag when the resume line alone cannot
survive deeper questioning. Flagged lines feed section 1 and the mock interview.

### 4. 刁钻问题

Gap-period, direction changes, short stints, being stuck on a question —
answers must be organized from the user's real experiences (ask for them);
never script fictional narratives. For real gaps use bridge answers: 承认缺口 →
相邻经验 → 正在进行的弥补.

### 5. 要问面试官的问题

4–6 questions tuned to the stage (筛选轮: 角色与团队; 技术轮: 技术与成长;
终面: 文化与方向). Drop anything public sources already answer.

### 6. 衔接模拟面试

End by offering: 是否现在用这个岗位做一次模拟面试？ On yes, follow the
standard mock-interview entry (fresh confirmed JD + resume, Blueprint flow).
Do not start interviewing inside this skill.

## Closing the loop

After any mock-interview review for this job, ask: 哪条表述被追问时撑不住了？
Facts the user confirms go through the normal Career Vault confirmation flow;
the next prep pack's section 1 must read these lessons first.

## Hard rules

- One job per pack; one section set; do not merge multiple stages silently.
- No claim beyond the confirmed resume; no coaching during the later mock
  interview itself (that is the interviewer's contract).
- Artifacts, if the user wants a file, go through the normal write approval.
