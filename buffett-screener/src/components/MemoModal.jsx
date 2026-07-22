import React from 'react';

// A simple, dependency-free markdown parser using regex
function parseMarkdown(md) {
  if (!md) return '';
  
  let html = md;
  
  // Escapes to prevent XSS
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
    
  // Headers
  html = html.replace(/^#\s+(.+)$/gm, '<h1 style="font-size: 1.75rem; line-height: 1.35; color: #1A6B3C; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px; margin-top: 0.5rem; margin-bottom: 1.5rem; font-weight: 700;">$1</h1>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2 style="font-size: 1.3rem; line-height: 1.4; color: #2E8B57; border-bottom: 1px solid #E2E8F0; padding-bottom: 6px; margin-top: 2rem; margin-bottom: 1rem; font-weight: 600;">$1</h2>');
  html = html.replace(/^###\s+(.+)$/gm, '<h3 style="font-size: 1.1rem; line-height: 1.4; color: #4A5568; margin-top: 1.5rem; margin-bottom: 0.8rem; font-weight: 600;">$1</h3>');
  
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Lists
  // Match unordered lists starting with '-' or '*'
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li style="margin-left: 1.5rem; margin-bottom: 6px; list-style-type: disc; line-height: 1.55; color: #2D3748;">$1</li>');
  
  // Wrap consecutive list items in <ul>
  // A simple hack: replace </li>\n<li with </li><li
  html = html.replace(/<\/li>\n<li/g, '</li><li');
  // Wrap list item groups
  html = html.replace(/(<li.*?>.*?<\/li>)/g, '<ul style="margin-bottom: 1rem;">$1</ul>');
  // Clean up duplicate nested tags
  html = html.replace(/<\/ul>\s*<ul.*?>/g, '');
  
  // Bullet point highlights
  html = html.replace(/•\s+(.+)$/gm, '<li style="margin-left: 1.5rem; margin-bottom: 6px; list-style-type: circle; line-height: 1.55; color: #2D3748;">$1</li>');

  // Paragraphs (split by double newlines, wrap in <p>)
  const blocks = html.split(/\n\n+/);
  const formattedBlocks = blocks.map(block => {
    // If block starts with HTML tag, don't wrap in <p> to avoid breaking lists/headers
    const trimmed = block.trim();
    if (trimmed.startsWith('<h1') || trimmed.startsWith('<h2') || trimmed.startsWith('<h3') || trimmed.startsWith('<ul') || trimmed.startsWith('<li')) {
      return trimmed;
    }
    return `<p style="line-height: 1.6; color: #2D3748; margin-bottom: 1rem; text-align: justify;">${trimmed}</p>`;
  });
  
  return formattedBlocks.join('\n');
}

export default function MemoModal({ ticker, companyName, content, onClose }) {
  const handlePrint = () => {
    window.print();
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100%',
      height: '100%',
      backgroundColor: 'rgba(0, 0, 0, 0.5)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 1000,
      padding: '1.5rem'
    }} className="memo-modal-overlay">
      
      {/* Inline styles to handle print and hide buttons */}
      <style>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .memo-print-container, .memo-print-container * {
            visibility: visible;
          }
          .memo-print-container {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            padding: 0;
            margin: 0;
            box-shadow: none !important;
            background: white !important;
          }
          .memo-modal-overlay {
            background-color: transparent !important;
            backdrop-filter: none !important;
            padding: 0 !important;
            position: relative !important;
          }
          .memo-header-buttons {
            display: none !important;
          }
        }
      `}</style>

      <div style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        boxShadow: '0 10px 25px rgba(0, 0, 0, 0.15)',
        width: '100%',
        maxWidth: '850px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        animation: 'slideUp 0.3s ease-out'
      }} className="memo-print-container">
        
        {/* Modal Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1.2rem 2rem',
          borderBottom: '1px solid #E2E8F0',
          backgroundColor: '#F8FAFC',
          borderTopLeftRadius: '12px',
          borderTopRightRadius: '12px'
        }} className="memo-header-buttons">
          <div>
            <h3 style={{ margin: 0, color: '#1A6B3C', fontSize: '1.25rem' }}>
              📝 Buy-Side Investment Memo
            </h3>
            <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 'bold' }}>
              {companyName} ({ticker})
            </span>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={handlePrint}
              style={{
                padding: '6px 14px',
                backgroundColor: '#E2E8F0',
                color: '#475569',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              🖨️ Print Memo
            </button>
            <button
              onClick={onClose}
              style={{
                padding: '6px 14px',
                backgroundColor: '#EF4444',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '0.85rem'
              }}
            >
              Close
            </button>
          </div>
        </div>

        {/* Modal Content */}
        <div style={{
          padding: '2.5rem 3rem',
          overflowY: 'auto',
          flexGrow: 1
        }}>
          <div 
            dangerouslySetInnerHTML={{ __html: parseMarkdown(content) }}
            style={{ fontFamily: 'Georgia, serif', fontSize: '1.05rem', color: '#1A202C' }}
          />
        </div>
        
      </div>
    </div>
  );
}
