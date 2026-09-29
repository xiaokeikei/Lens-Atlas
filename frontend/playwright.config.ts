import { defineConfig } from '@playwright/test';
import path from 'node:path';
const python=path.resolve('..','.venv','Scripts','python.exe');
export default defineConfig({testDir:'tests',timeout:90000,use:{baseURL:'http://127.0.0.1:18765',viewport:{width:1440,height:1050},screenshot:'only-on-failure'},workers:1,reporter:[['list']],webServer:[
  {command:'"'+python+'" ../scripts/dev_fixture_server.py',url:'http://127.0.0.1:18765/api/health',reuseExistingServer:false,timeout:30000},
  {command:'"'+python+'" ../scripts/dev_fixture_server.py --nas',url:'http://127.0.0.1:18766/api/health',reuseExistingServer:false,timeout:30000}
]});
