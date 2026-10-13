/* Minimal inline icon set (stroke icons, 24px grid). No external icon font → works offline & under CSP. */
const P: Record<string, string> = {
  dashboard: "M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z",
  write: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
  bible: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11",
  timeline: "M3 12h18M7 8v8M12 5v14M17 9v6",
  graph: "M6 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M12 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7.5 7.5l3.5 9M16.5 7.5l-3.5 9M8 6h8",
  continuity: "M12 3l9 16H3zM12 10v4M12 17h.01",
  sources: "M4 4h6l2 2h8v14H4zM8 12h8M8 16h5",
  agents: "M12 3v3M5 9h14v10H5zM9 13h.01M15 13h.01M9 17h6M3 13h2M19 13h2",
  proposals: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9",
  publish: "M12 3v12M7 10l5 5 5-5M5 21h14",
  insight: "M3 3v18h18M7 15l4-4 3 3 5-6",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.1 19.8l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 14.4H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.2 7.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9.6 3V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1.3z",
  admin: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7zM9 12l2 2 4-4",
  projects: "M3 7h18v13H3zM3 7l3-4h12l3 4",
  plus: "M12 5v14M5 12h14",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 3",
  check: "M5 12l5 5L20 7",
  x: "M6 6l12 12M18 6L6 18",
  play: "M7 4v16l13-8z",
  stop: "M6 6h12v12H6z",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  panelL: "M3 4h18v16H3zM15 4v16",
  panelR: "M3 4h18v16H3zM9 4v16",
  bold: "M6 4h8a4 4 0 0 1 0 8H6zM6 12h9a4 4 0 0 1 0 8H6z",
  italic: "M19 4h-9M14 20H5M15 4L9 20",
  quote: "M7 7h4v6H5V9a2 2 0 0 1 2-2zM17 7h4v6h-6V9a2 2 0 0 1 2-2zM5 13c0 3 2 4 4 4M15 13c0 3 2 4 4 4",
  heading: "M6 4v16M18 4v16M6 12h12",
  footnote: "M4 6h10M4 12h10M4 18h7M18 4v6M16 6l2-2 2 2",
  ltr: "M4 6h12M4 12h8M4 18h12M18 9l3 3-3 3",
  rtl: "M8 6h12M12 12h8M8 18h12M6 9l-3 3 3 3",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3",
  redo: "M15 14l5-5-5-5M20 9H10a6 6 0 0 0 0 12h3",
  find: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-6-6M7 10h6",
  cloud: "M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19 10a4 4 0 0 1-1 8z",
  cloudOff: "M3 3l18 18M9.5 6.3A6 6 0 0 1 19 10a4 4 0 0 1 1.6 7.4M17 18H7a5 5 0 0 1-1.8-9.7",
  shield: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  upload: "M12 20V8M7 13l5-5 5 5M5 4h14",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  map: "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
  spark: "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  scan: "M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M4 12h16",
};

export function Icon({ name, size = 18, className }: { name: keyof typeof P | string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      <path d={P[name] || P.spark} />
    </svg>
  );
}

export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#84DCC6" />
      {/* a pen nib — «كاتب» */}
      <path d="M32 10 L45 33 L32 54 L19 33 Z" fill="#0F2E28" />
      <path d="M32 33 V54" stroke="#84DCC6" strokeWidth="2.5" />
      <circle cx="32" cy="31" r="4.5" fill="#FF686B" />
    </svg>
  );
}
