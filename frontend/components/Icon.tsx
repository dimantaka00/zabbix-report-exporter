import type {ReactNode, SVGProps} from "react";

const paths = {
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
  moon: <path d="M20.9 13.2A9 9 0 0 1 10.8 3.1 9 9 0 1 0 20.9 13.2Z"/>,
  monitor: <><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 21h8M12 16v5M7 10h2l2-3 2 6 2-3h2"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2M8 18h2"/></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5"/></>,
  server: <><rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></>,
  activity: <><path d="M3 12h4l3-8 4 16 3-8h4"/></>,
  layers: <><path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5M5.5 7a7 7 0 0 1 11-2l3.5 3M4 16l3.5 3a7 7 0 0 0 11-2"/></>,
  shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM9 12l2 2 4-4"/></>,
  sliders: <><path d="M4 5h6M14 5h6M4 12h2M10 12h10M4 19h10M18 19h2"/><circle cx="12" cy="5" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="19" r="2"/></>,
  chart: <><path d="M3 3v18h18M7 14l4-5 4 3 5-7"/></>,
  history: <><path d="M3 10a9 9 0 1 1 1 7M3 4v6h6M12 7v5l3 2"/></>,
  download: <><path d="M12 3v12M7 10l5 5 5-5M4 16v5h16v-5"/></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  network: <><rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/></>,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof paths;
export default function Icon({name,className="",...props}: {name:IconName} & SVGProps<SVGSVGElement>) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"
    className={`icon ${className}`} {...props}>{paths[name]}</svg>;
}
