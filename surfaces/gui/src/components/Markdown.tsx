import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { isAlpha } from "../api";
import { Icon } from "./Icon";

// §34 (UX-016): the agent ends a deliverable turn with plain markdown —
// [Title](artifact:relative/path) — and the renderer turns it into a chip that opens the
// artifact viewer in place. Plumbing is a window event (the viewer lives in RightRail;
// this component renders deep inside the transcript): RightRail resolves the path against
// the session's artifact list, App un-hides the rail.
export const OPEN_ARTIFACT_EVENT = "ocw-open-artifact";

const URL_SENTENCE_PUNCTUATION = /[。，；：！？、]/u;
const URL_CLOSING_PUNCTUATION = /[）】》」』〉]/u;

function splitBareUrlText(value: string): [string, string] | null {
  const punctuationIndex = value.search(URL_SENTENCE_PUNCTUATION);
  if (punctuationIndex < 0) return null;

  let urlEnd = punctuationIndex;
  while (urlEnd > 0 && URL_CLOSING_PUNCTUATION.test(value[urlEnd - 1])) {
    urlEnd -= 1;
  }
  return [value.slice(0, urlEnd), value.slice(urlEnd)];
}

function ArtifactChip({ path, title }: { path: string; title: string }) {
  const file = path.split("/").pop() || path;
  return (
    <button
      className="art-chip"
      data-testid="artifact-chip"
      title={path}
      onClick={() =>
        window.dispatchEvent(new CustomEvent(OPEN_ARTIFACT_EVENT, { detail: { path } }))
      }
    >
      <span className="art-chip-ico">
        <Icon name="file" size={14} />
      </span>
      <span className="art-chip-meta">
        <b>{title || file}</b>
        {title && title !== file && <span>{file}</span>}
      </span>
      <span className="art-chip-open">打开 ›</span>
    </button>
  );
}

// Assistant messages rendered as GitHub-flavored markdown (headings, lists, tables, code,
// links). Links open externally — never navigate the app shell — except artifact: links,
// which open the session's artifact viewer.
export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // artifact: is ours — keep it through the sanitizer (everything else gets the default
        // http/https/mailto policy).
        urlTransform={(url) => (url.startsWith("artifact:") ? url : defaultUrlTransform(url))}
        components={{
          img: ({ node: _node, ...props }) =>
            isAlpha() ? (
              <span title="为保护隐私，云端对话不自动加载图片。">图片未自动加载</span>
            ) : (
              <img {...props} />
            ),
          a: ({ node, href, children, ...props }) => {
            if (href?.startsWith("artifact:")) {
              const title = Array.isArray(children) ? children.join("") : String(children ?? "");
              return <ArtifactChip path={href.slice("artifact:".length)} title={title} />;
            }
            const sourceOffset = node?.position?.start.offset;
            const bareUrlText =
              href?.match(/^https?:\/\//) &&
              typeof children === "string" &&
              typeof sourceOffset === "number" &&
              text.startsWith(children, sourceOffset)
                ? splitBareUrlText(children)
                : null;
            if (bareUrlText) {
              const [url, suffix] = bareUrlText;
              return (
                <>
                  <a
                    href={defaultUrlTransform(url)}
                    {...props}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {url}
                  </a>
                  {suffix}
                </>
              );
            }
            return (
              <a href={href} {...props} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
