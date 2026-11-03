import React from 'react';
import { BrowserRouter } from 'react-router-dom'; // 引入路由核心容器
import ReactDOM from 'react-dom/client';
import './App.css';
import App from './App.jsx';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    {/* 用BrowserRouter包裹App，让整个应用拥有路由能力 */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);