export const THEME_KEY = "zabbix-report-theme";
export type Theme = "light" | "dark";
export const DEFAULT_THEME: Theme = "dark";

// Apply the stored preference in the document head before the first paint.
export const THEME_INIT_SCRIPT = `(function(){var theme=null;try{theme=localStorage.getItem(${JSON.stringify(THEME_KEY)})}catch(e){}if(theme!=="light"&&theme!=="dark"){theme=${JSON.stringify(DEFAULT_THEME)}}document.documentElement.dataset.theme=theme})()`;
