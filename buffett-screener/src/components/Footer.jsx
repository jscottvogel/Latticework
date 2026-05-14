import React from 'react';
import './Footer.css';

export default function Footer() {
  return (
    <footer className="app-footer">
      <div className="footer-content">
        <p>
          This application is for research and educational purposes only. It does not
          constitute financial advice. Past screening results do not guarantee future
          investment performance. Always conduct your own due diligence before making
          any investment decisions. The creators of this tool are not registered
          investment advisors.
        </p>
      </div>
    </footer>
  );
}
