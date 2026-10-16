import { describe, expect, it } from "vitest";

import app from "./App.tsx?raw";
import composer from "./components/Composer.tsx?raw";
import inbox from "./components/InboxItemCard.tsx?raw";
import inboxView from "./components/InboxView.tsx?raw";
import integrations from "./components/IntegrationsView.tsx?raw";
import plan from "./components/PlanCard.tsx?raw";
import rightRail from "./components/RightRail.tsx?raw";
import scheduled from "./components/ScheduledView.tsx?raw";
import search from "./components/SearchModal.tsx?raw";
import settings from "./components/SettingsView.tsx?raw";
import sidebar from "./components/Sidebar.tsx?raw";
import skills from "./components/SkillsTab.tsx?raw";

const SOURCES = {
  App: app,
  Composer: composer,
  InboxItemCard: inbox,
  InboxView: inboxView,
  IntegrationsView: integrations,
  PlanCard: plan,
  RightRail: rightRail,
  ScheduledView: scheduled,
  SearchModal: search,
  SettingsView: settings,
  Sidebar: sidebar,
  SkillsTab: skills,
};

const FORBIDDEN = [
  /\bNew session\b/,
  /\bSearch chats\b/,
  /\bNo chats found\b/,
  /\bChoose a persona\b/,
  /\bStart a session as\b/,
  /\bManage personas\b/,
  /\bSession actions\b/,
  /\bGroup (?:and|&) filter conversations\b/,
  /\bAutomations\b/,
  /\bLoading models\b/,
  /\bNo model\b/,
  /\bConnect a model\b/,
  /\bToken usage\b/,
  /\bSend approvals to (?:the )?Inbox\b/,
  /\bThe agent proposed a plan\b/,
  /\bApprove & run\b/,
  /\bSend feedback\b/,
  /\bBack to artifacts\b/,
  /\bOpen in default app\b/,
  /\bSettings\b/,
  /\bAppearance\b/,
  /\bVoice input\b/,
  /\bTrusted workspaces\b/,
  /\bNew automation\b/,
  /\bCreate automation\b/,
  /\bNo scheduled tasks yet\b/,
  /\bDelete automation\b/,
  /\bInbox\b/,
  /\bConnectors\b/,
  /\bMCP servers\b/,
  /\bSave skill\b/,
  /\bAdd skill\b/,
];

describe("Chinese interaction copy audit", () => {
  it("contains no known English interaction labels on primary GUI surfaces", () => {
    const failures = Object.entries(SOURCES).flatMap(([name, source]) =>
      FORBIDDEN.filter((pattern) =>
        pattern.test(
          source
            .replace(/\/\*[\s\S]*?\*\//g, "")
            .replace(/\/\/.*$/gm, ""),
        ),
      ).map((pattern) => `${name}: ${pattern}`),
    );

    expect(failures).toEqual([]);
  });
});
