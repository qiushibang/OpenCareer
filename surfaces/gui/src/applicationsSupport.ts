/** The personal application workspace (求职进度) exists on the local build and the hosted alpha build. */
export const supportsApplications = (): boolean =>
  ["standalone", "alpha"].includes(String((import.meta as any).env?.MODE));
