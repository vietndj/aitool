/**
 * repo-hub-widget.js — Universal Repo Hub Auto-Discovery & Poster Grid Widget
 * Tự động đọc ./posts-manifest.json và hiển thị Kho Bài Viết kèm Poster Điện Ảnh
 * ngay trên các trang chủ có sẵn Landing Page mà không làm ảnh hưởng giao diện gốc.
 */
(function () {
  if (window.__UNIVERSAL_REPO_HUB_WIDGET_LOADED__) return;
  window.__UNIVERSAL_REPO_HUB_WIDGET_LOADED__ = true;

  async function initRepoHubWidget() {
    try {
      const res = await fetch('./posts-manifest.json?t=' + Date.now());
      if (!res.ok) return;
      const manifest = await res.json();
      const posts = Array.isArray(manifest.posts) ? manifest.posts : [];
      if (posts.length === 0) return;

      const style = document.createElement('style');
      style.textContent = `
        #urh-section {
          position: relative;
          z-index: 40;
          background: #080b12;
          color: #f8fafc;
          padding: 64px 20px 88px;
          border-top: 1px solid rgba(56, 189, 248, 0.22);
          font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
          scroll-snap-align: start;
          min-height: auto;
          height: auto !important;
          overflow: visible !important;
        }
        #urh-container {
          max-width: 1280px;
          margin: 0 auto;
        }
        .urh-header {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: flex-end;
          gap: 16px;
          margin-bottom: 28px;
          padding-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .urh-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 12px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          background: rgba(16, 185, 129, 0.14);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.3);
          margin-bottom: 10px;
        }
        .urh-title {
          font-size: clamp(22px, 3vw, 30px);
          font-weight: 800;
          color: #ffffff;
          margin: 0;
          line-height: 1.25;
        }
        .urh-sub {
          font-size: 13.5px;
          color: #94a3b8;
          margin-top: 6px;
        }
        .urh-controls {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
        }
        .urh-search {
          background: #111827;
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #fff;
          padding: 10px 14px;
          border-radius: 10px;
          font-size: 13px;
          min-width: 240px;
          outline: none;
        }
        .urh-search:focus {
          border-color: #38bdf8;
        }
        .urh-hub-btn {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: linear-gradient(135deg, #059669, #0284c7);
          color: #fff !important;
          text-decoration: none !important;
          font-size: 13px;
          font-weight: 700;
          padding: 10px 16px;
          border-radius: 10px;
          transition: transform 0.18s ease, opacity 0.18s ease;
        }
        .urh-hub-btn:hover {
          transform: translateY(-2px);
          opacity: 0.95;
        }
        .urh-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
          gap: 18px;
        }
        .urh-card {
          background: #111827;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          overflow: hidden;
          text-decoration: none !important;
          color: inherit !important;
          display: flex;
          flex-direction: column;
          transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
        }
        .urh-card:hover {
          transform: translateY(-4px);
          border-color: rgba(56, 189, 248, 0.5);
          box-shadow: 0 14px 30px -10px rgba(0, 0, 0, 0.65);
        }
        .urh-cover-wrap {
          width: 100%;
          aspect-ratio: 3 / 4;
          background: #1e293b;
          overflow: hidden;
          position: relative;
        }
        .urh-cover-wrap img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
          transition: transform 0.4s ease;
        }
        .urh-card:hover .urh-cover-wrap img {
          transform: scale(1.05);
        }
        .urh-cat-pill {
          position: absolute;
          top: 10px;
          left: 10px;
          background: rgba(8, 11, 18, 0.84);
          backdrop-filter: blur(8px);
          color: #38bdf8;
          font-size: 10px;
          font-weight: 700;
          padding: 4px 9px;
          border-radius: 6px;
          border: 1px solid rgba(56, 189, 248, 0.28);
        }
        .urh-body {
          padding: 14px;
          display: flex;
          flex-direction: column;
          flex: 1;
        }
        .urh-card-title {
          font-size: 14.5px;
          font-weight: 700;
          color: #f8fafc;
          line-height: 1.38;
          margin: 0 0 6px;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .urh-card-excerpt {
          font-size: 12px;
          color: #94a3b8;
          line-height: 1.5;
          margin: 0 0 12px;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          flex: 1;
        }
        .urh-card-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 11px;
          color: #64748b;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          padding-top: 8px;
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        #urh-fab {
          position: fixed;
          bottom: 18px;
          left: 18px;
          z-index: 9990;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: rgba(15, 23, 42, 0.92);
          backdrop-filter: blur(12px);
          color: #f8fafc !important;
          border: 1px solid rgba(56, 189, 248, 0.4);
          padding: 9px 15px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          text-decoration: none !important;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
          cursor: pointer;
          transition: all 0.2s ease;
        }
        #urh-fab:hover {
          background: #0284c7;
          border-color: #38bdf8;
          transform: translateY(-2px);
        }
      `;
      document.head.appendChild(style);

      const section = document.createElement('section');
      section.id = 'urh-section';
      section.innerHTML = `
        <div id="urh-container">
          <div class="urh-header">
            <div>
              <div class="urh-badge">⚡ AUTO-DISCOVERY MANIFEST • ${posts.length} TÀI LIỆU</div>
              <h2 class="urh-title">Kho Bài Viết & Tài Liệu Trong Repo (${manifest.site_id || 'Hub'})</h2>
              <div class="urh-sub">Tự động cập nhật 100% file HTML mới tải lên repo kèm Poster Tiên Hiệp • Cổ Trang • Liên Minh Huyền Thoại</div>
            </div>
            <div class="urh-controls">
              <input type="text" id="urh-search-input" class="urh-search" placeholder="Tìm nhanh trong ${posts.length} bài viết..." />
              <a href="./hub.html" class="urh-hub-btn">
                <span>🧭 Mở Trang Chủ Hub 3 Cột</span>
              </a>
            </div>
          </div>
          <div id="urh-grid" class="urh-grid"></div>
        </div>
      `;
      document.body.appendChild(section);

      const fab = document.createElement('a');
      fab.id = 'urh-fab';
      fab.href = '#urh-section';
      fab.innerHTML = `<span>🗂️ Kho Bài Viết (${posts.length})</span>`;
      document.body.appendChild(fab);

      const grid = document.getElementById('urh-grid');
      const searchInput = document.getElementById('urh-search-input');

      function removeAccents(str) {
        return (str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
      }

      function renderCards(filterText) {
        const q = removeAccents(filterText.trim());
        const filtered = posts.filter(p => {
          if (!q) return true;
          return removeAccents(p.title + ' ' + p.filename + ' ' + (p.excerpt || '')).includes(q);
        });
        grid.innerHTML = filtered.map(p => `
          <a class="urh-card" href="./${p.filename}" target="_blank">
            <div class="urh-cover-wrap">
              <img src="${p.cover_image}" alt="${(p.title || '').replace(/"/g, '&quot;')}" loading="lazy" />
              <span class="urh-cat-pill">${p.category_label || '📌 Tài liệu'}</span>
            </div>
            <div class="urh-body">
              <h3 class="urh-card-title">${p.title}</h3>
              <p class="urh-card-excerpt">${p.excerpt || ''}</p>
              <div class="urh-card-meta">
                <span>${p.filename.replace(/\.html$/, '')}</span>
                <span>${p.read_time || '5 phút'}</span>
              </div>
            </div>
          </a>
        `).join('');
      }

      renderCards('');
      if (searchInput) {
        searchInput.addEventListener('input', e => renderCards(e.target.value));
      }
    } catch (err) {
      console.warn('Universal Repo Hub Widget error:', err);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRepoHubWidget);
  } else {
    initRepoHubWidget();
  }
})();
