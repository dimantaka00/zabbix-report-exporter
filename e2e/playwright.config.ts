import {defineConfig,devices} from "@playwright/test";
export default defineConfig({
  testDir:"./tests",timeout:30000,fullyParallel:true,forbidOnly:!!process.env.CI,
  retries:0,workers:2,reporter:[["list"],["html",{open:"never"}]],
  use:{channel:process.env.E2E_BROWSER_CHANNEL || "chrome",baseURL:process.env.E2E_BASE_URL || "http://127.0.0.1:3301",trace:"retain-on-failure",screenshot:"only-on-failure"},
  projects:[
    {name:"desktop",use:{...devices["Desktop Chrome"]}},
    {name:"mobile",use:{...devices["Pixel 7"]}},
  ],
});
