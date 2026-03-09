---
title: "로컬 영수증 단축어 설치"
date: 2026-03-09
draft: false
description: "로컬 영수증 앱의 iOS Shortcuts 단축어를 설치하세요. 카드 문자 수신 시 자동으로 거래내역을 기록합니다."
_build:
  list: never
  render: always
sitemap:
  priority: 0
  changefreq: never
hidemeta: true
ShowBreadCrumbs: false
ShowReadingTime: false
ShowShareButtons: false
ShowPostNavLinks: false
---

<style>
  .shortcut-page {
    max-width: 480px;
    margin: 0 auto;
    padding: 40px 20px;
    text-align: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }
  .app-icon {
    width: 80px;
    height: 80px;
    background: linear-gradient(135deg, #3B82F6, #1D4ED8);
    border-radius: 20px;
    margin: 0 auto 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 40px;
    box-shadow: 0 8px 24px rgba(59,130,246,0.3);
  }
  .page-title {
    font-size: 24px;
    font-weight: 800;
    margin: 0 0 8px;
    color: inherit;
  }
  .page-desc {
    font-size: 15px;
    color: #6B7280;
    margin: 0 0 32px;
    line-height: 1.6;
  }
  .install-btn {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: #3B82F6;
    color: #fff !important;
    text-decoration: none !important;
    padding: 16px 32px;
    border-radius: 14px;
    font-size: 17px;
    font-weight: 700;
    box-shadow: 0 4px 16px rgba(59,130,246,0.4);
    transition: transform 0.15s, box-shadow 0.15s;
    margin-bottom: 16px;
  }
  .install-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(59,130,246,0.5);
  }
  .install-btn svg {
    flex-shrink: 0;
  }
  .steps {
    background: #F9FAFB;
    border-radius: 16px;
    padding: 24px;
    margin-top: 32px;
    text-align: left;
  }
  .dark .steps { background: #1F2937; }
  .steps-title {
    font-size: 14px;
    font-weight: 700;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 16px;
  }
  .step {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 14px;
  }
  .step:last-child { margin-bottom: 0; }
  .step-num {
    width: 24px;
    height: 24px;
    background: #3B82F6;
    color: #fff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
  }
  .step-text { font-size: 14px; line-height: 1.5; }
  .step-text strong { display: block; margin-bottom: 2px; }
  .note {
    font-size: 12px;
    color: #9CA3AF;
    margin-top: 24px;
    line-height: 1.6;
  }
</style>

<div class="shortcut-page">
  <div class="app-icon">🧾</div>
  <h1 class="page-title">로컬 영수증 단축어</h1>
  <p class="page-desc">아래 버튼을 탭하면 iOS Shortcuts 앱에서<br>단축어를 바로 추가할 수 있습니다.</p>

  <a class="install-btn" href="shortcuts://import?url=https://seunghan.xyz/slipbox/localreceipt.shortcut">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
      <polyline points="13 2 13 9 20 9"/>
    </svg>
    단축어 설치하기
  </a>

  <div class="steps">
    <div class="steps-title">설치 후 자동화 연결 방법</div>
    <div class="step">
      <div class="step-num">1</div>
      <div class="step-text"><strong>단축어 설치</strong>위 버튼으로 '로컬 영수증에 추가' 단축어를 추가하세요.</div>
    </div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-text"><strong>자동화 탭 이동</strong>Shortcuts 앱 → 하단 '자동화' 탭 → '+' 버튼</div>
    </div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-text"><strong>트리거 설정</strong>'메시지' 선택 → 카드사 번호(예: 1588-xxxx) 수신 시</div>
    </div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-text"><strong>단축어 연결</strong>'로컬 영수증에 추가' 단축어를 실행하도록 설정</div>
    </div>
  </div>

  <p class="note">
    ⚠️ iPhone에서만 동작합니다.<br>
    단축어 설치 후 앱이 없으시면 App Store에서 '로컬 영수증'을 검색해 설치하세요.
  </p>
</div>
