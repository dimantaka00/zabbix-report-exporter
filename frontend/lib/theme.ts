export const THEME_KEY = "zabbix-report-theme";
export type Theme = "light" | "dark";

// Apply the stored preference in the document head before the first paint.
export const THEME_INIT_SCRIPT = `(function(){var theme=null;try{theme=localStorage.getItem(${JSON.stringify(THEME_KEY)})}catch(e){}if(theme!=="light"&&theme!=="dark"){theme=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=theme})()`;
