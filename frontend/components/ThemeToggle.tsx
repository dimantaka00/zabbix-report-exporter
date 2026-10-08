"use client";
import {useEffect, useRef, useState} from "react";
import {THEME_KEY, type Theme} from "../lib/theme";
import Icon from "./Icon";

export default function ThemeToggle() {
  const [theme,setTheme]=useState<Theme>("light");
  const preference=useRef<Theme | null>(null);
  useEffect(()=>{
    const system=window.matchMedia("(prefers-color-scheme: dark)");
    const sync=()=>{
      let stored:string | null=null;
      try {stored=localStorage.getItem(THEME_KEY);} catch { /* Keep the in-memory preference. */ }
      const selected=stored==="light" || stored==="dark" ? stored : preference.current;
      const next=selected || (system.matches ? "dark" : "light");
      document.documentElement.dataset.theme=next;
      setTheme(next);
    };
    const onStorage=(event:StorageEvent)=>{
      if(event.key===THEME_KEY || event.key===null) {
        preference.current=event.newValue==="light" || event.newValue==="dark" ? event.newValue : null;
        sync();
      }
    };
    sync();
    system.addEventListener("change",sync);
    window.addEventListener("storage",onStorage);
    return ()=>{system.removeEventListener("change",sync);window.removeEventListener("storage",onStorage);};
  },[]);
  function toggle() {
    const next=document.documentElement.dataset.theme==="dark" ? "light" : "dark";
    preference.current=next;
    document.documentElement.dataset.theme=next;
    setTheme(next);
    try {localStorage.setItem(THEME_KEY,next);} catch { /* The toggle also works without browser storage. */ }
  }
  return <button type="button" className="theme-toggle" role="switch" aria-label="Mode gelap"
    aria-checked={theme==="dark"} title={`Aktifkan mode ${theme==="dark" ? "terang" : "gelap"}`} onClick={toggle}>
    <span className="theme-light-label"><Icon name="sun"/>Mode terang</span>
    <span className="theme-dark-label"><Icon name="moon"/>Mode gelap</span>
  </button>;
}
