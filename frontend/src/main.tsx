import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import UsageNotice from './UsageNotice';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><UsageNotice><App /></UsageNotice></React.StrictMode>);
