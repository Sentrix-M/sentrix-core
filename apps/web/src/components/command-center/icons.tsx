import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function base(props: IconProps): IconProps {
  return {
    xmlns: "http://www.w3.org/2000/svg",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    ...props,
  };
}

/**
 * Accessible SVG shell. Icons are rendered with `aria-hidden` (they are
 * decorative companions next to text labels), and a `<title>` is provided
 * to satisfy a11y linting and non-visual contexts.
 */
function Svg({
  title,
  children,
  ...props
}: IconProps & { title: string; children: React.ReactNode }) {
  return (
    <svg {...base(props)}>
      <title>{title}</title>
      {children}
    </svg>
  );
}

/** Sentrix brand mark — cyber shield with core. */
export function LogoIcon(props: IconProps) {
  return (
    <Svg title="Sentrix" {...props}>
      <path d="M12 2.5 4.5 5.5v6c0 4.5 3.2 7.8 7.5 10 4.3-2.2 7.5-5.5 7.5-10v-6L12 2.5Z" />
      <path d="M12 8v4.2" />
      <circle cx="12" cy="14.5" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function GridIcon(props: IconProps) {
  return (
    <Svg title="Command Center" {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </Svg>
  );
}

export function SparklesIcon(props: IconProps) {
  return (
    <Svg title="AI" {...props}>
      <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3Z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z" />
      <path d="M5 16l.7 1.6L7.5 18.3l-1.8.7L5 20.6l-.7-1.6-1.8-.7 1.8-.7L5 16Z" />
    </Svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Svg title="Alert" {...props}>
      <path d="M10.3 3.9 2.6 17.1A1.6 1.6 0 0 0 4 19.5h16a1.6 1.6 0 0 0 1.4-2.4L13.7 3.9a1.7 1.7 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <circle cx="12" cy="16.5" r="0.4" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function RadarIcon(props: IconProps) {
  return (
    <Svg title="Incidents" {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 12 19 5" />
      <circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function CrosshairIcon(props: IconProps) {
  return (
    <Svg title="Threat Hunting" {...props}>
      <circle cx="12" cy="12" r="7.5" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <Svg title="Knowledge" {...props}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z" />
      <path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />
    </Svg>
  );
}

export function WrenchIcon(props: IconProps) {
  return (
    <Svg title="Tools" {...props}>
      <path d="M14.7 6.3a4.5 4.5 0 0 0-6 5.6L3 17.6V21h3.4l5.7-5.7a4.5 4.5 0 0 0 5.6-6L15 12l-3-3 2.7-2.7Z" />
    </Svg>
  );
}

export function PlugIcon(props: IconProps) {
  return (
    <Svg title="Integrations" {...props}>
      <path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0V8Z" />
      <path d="M12 17v5" />
    </Svg>
  );
}

export function ReportIcon(props: IconProps) {
  return (
    <Svg title="Reports" {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8M8 17h5" />
    </Svg>
  );
}

export function GearIcon(props: IconProps) {
  return (
    <Svg title="Settings" {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1Z" />
    </Svg>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <Svg title="Menu" {...props}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </Svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg title="Search" {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <Svg title="Notifications" {...props}>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </Svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <Svg title="Send" {...props}>
      <path d="m22 2-7 20-4-9-9-4 20-7Z" />
      <path d="M22 2 11 13" />
    </Svg>
  );
}

export function MicIcon(props: IconProps) {
  return (
    <Svg title="Microphone" {...props}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8" />
    </Svg>
  );
}

export function CpuIcon(props: IconProps) {
  return (
    <Svg title="Kernel" {...props}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <rect x="10" y="10" width="4" height="4" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </Svg>
  );
}

export function MemoryIcon(props: IconProps) {
  return (
    <Svg title="Memory" {...props}>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M6 9v6M10 9v6M14 9v6M18 9v6M2 12h20" />
    </Svg>
  );
}

export function BrainIcon(props: IconProps) {
  return (
    <Svg title="Reasoning" {...props}>
      <path d="M9.5 4A2.5 2.5 0 0 0 7 6.5C5.6 7 4.5 8.3 4.5 9.8c0 .9.4 1.7 1 2.2-.6.5-1 1.3-1 2.2 0 1.6 1.3 2.9 3 3.4.4 1.2 1.5 2.1 2.9 2.1 1.6 0 3-1.3 3-2.9V6.7A2.7 2.7 0 0 0 9.5 4Z" />
      <path d="M14.5 4A2.5 2.5 0 0 1 17 6.5c1.4.5 2.5 1.8 2.5 3.3 0 .9-.4 1.7-1 2.2.6.5 1 1.3 1 2.2 0 1.6-1.3 2.9-3 3.4-.4 1.2-1.5 2.1-2.9 2.1-1.6 0-3-1.3-3-2.9V6.7A2.7 2.7 0 0 1 14.5 4Z" />
    </Svg>
  );
}

export function LayersIcon(props: IconProps) {
  return (
    <Svg title="Sources" {...props}>
      <path d="m12 2 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </Svg>
  );
}

export function ConnectionIcon(props: IconProps) {
  return (
    <Svg title="Connection" {...props}>
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="12" cy="18" r="2.5" />
      <path d="M8 7.5 10.5 15.7M16 7.5 13.5 15.7M8.5 6h7" />
    </Svg>
  );
}

export function DatabaseIcon(props: IconProps) {
  return (
    <Svg title="Knowledge Base" {...props}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </Svg>
  );
}

export function VoiceIcon(props: IconProps) {
  return (
    <Svg title="Voice" {...props}>
      <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 11a7 7 0 0 1-14 0" />
      <path d="M12 18v4" />
    </Svg>
  );
}

export function TargetIcon(props: IconProps) {
  return (
    <Svg title="Confidence" {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function FileScanIcon(props: IconProps) {
  return (
    <Svg title="Analyze File" {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" />
      <path d="M14 2v6h6" />
      <path d="M9 15l1.5-.4a3 3 0 0 0 2-4.6l-1-1L9.5 10" />
      <path d="m14.5 11.5-1.5.4a3 3 0 0 0-2 4.6l1 1 1-1.5" />
    </Svg>
  );
}

export function ScrollIcon(props: IconProps) {
  return (
    <Svg title="Investigations" {...props}>
      <path d="M5 4h13a2 2 0 0 1 2 2v1H7a2 2 0 0 1 0-4V4Z" />
      <path d="M5 4a2 2 0 0 0-2 2v2" />
      <path d="M3 8h2v13h13" />
      <path d="M7 3v13" />
      <path d="M11 8h6M11 12h6" />
    </Svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg title="Evidence" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </Svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg title="Open" {...props}>
      <path d="m9 18 6-6-6-6" />
    </Svg>
  );
}

export function ArrowUpRightIcon(props: IconProps) {
  return (
    <Svg title="Open in new tab" {...props}>
      <path d="M7 17 17 7M8 7h9v9" />
    </Svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg title="Time" {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3 2" />
    </Svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <Svg title="Shield" {...props}>
      <path d="M12 2.5 4.5 5.5v6c0 4.5 3.2 7.8 7.5 10 4.3-2.2 7.5-5.5 7.5-10v-6L12 2.5Z" />
      <path d="m8.5 12 2.2 2.2 4.8-5" />
    </Svg>
  );
}

export function BoltIcon(props: IconProps) {
  return (
    <Svg title="Real-time" {...props}>
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
    </Svg>
  );
}

export function FilterIcon(props: IconProps) {
  return (
    <Svg title="Filter" {...props}>
      <path d="M3 5h18l-7 8v6l-4-2v-4L3 5Z" />
    </Svg>
  );
}
