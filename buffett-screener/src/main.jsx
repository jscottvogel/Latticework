import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

import { Amplify } from 'aws-amplify';
// In Gen 2, the configuration is auto-generated as amplify_outputs.json.
// Assuming it exists or will be generated during build/sandbox.
try {
  const outputs = require('../amplify_outputs.json');
  Amplify.configure(outputs);
} catch (e) {
  console.warn('amplify_outputs.json not found, using dummy config or waiting for deploy.');
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
