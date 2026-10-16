# Upstream attribution

OpenCareer is an independent career-focused derivative of
[OpenWorker](https://github.com/andrewyng/openworker), licensed under MIT.
The original copyright and permission notice are retained in `LICENSE`.

The initial integration baseline was commit
`01b6f83b3927e02912dda84bb392942c13ca70d1` (2026-08-01).
OpenCareer adds the Career domain, personas and skills, job-source adapters,
resume workflows, mock interviews, hosted identity and tenant isolation, feedback,
security hardening and local distribution support. The upstream runtime remains
the foundation for conversation orchestration, tool permissions and model routing.

The public repository starts from a sanitized source snapshot. Earlier private
operational history is intentionally not published; this does not remove or replace
upstream copyright. Repository history length is not a claim of sole authorship.

Bundled dependencies retain their own notices: see `deploy/vendor/README.md` and
`surfaces/gui/vendor/`. OCR / speech models and external services are separate from
the MIT license granted for this source code. No upstream signing keys or update
service are provided by this project.
