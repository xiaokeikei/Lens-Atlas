import { defineConfig } from '@playwright/test';
import path from 'node:path';
export default defineConfig({testDir:'mobile-tests',outputDir:'../.runtime/mobile-playwright-results',timeout:45000,workers:1,use:{baseURL:'http://127.0.0.1:18768',viewport:{width:390,height:844},deviceScaleFactor:1},reporter:'list',webServer:{command:'"'+path.resolve('../.venv/Scripts/python.exe')+'" -m http.server 18768 --bind 127.0.0.1 --directory dist-mobile',url:'http://127.0.0.1:18768/mobile.html',reuseExistingServer:false}});
