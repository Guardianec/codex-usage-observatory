import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./frontend/e2e',timeout:30000,workers:1,
  use:{baseURL:'http://127.0.0.1:8877',viewport:{width:1440,height:900},trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:{command:'python -u -m scripts.e2e_server',url:'http://127.0.0.1:8877/api/health',reuseExistingServer:false,timeout:30000},
  reporter:[['list']]
});
