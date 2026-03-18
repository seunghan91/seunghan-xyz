---
title: "PassPass에 오신 걸 환영합니다"
date: 2026-03-18
draft: false
description: "PassPass 확장프로그램 설치 완료! 간편인증 자동입력 시작하기"
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
.pp-welcome { max-width: 720px; margin: 0 auto; }
.pp-badge {
  display: inline-flex; align-items: center; gap: 7px;
  background: #f0fdf9; border: 1px solid #b2e8e2; border-radius: 30px;
  padding: 7px 18px; font-size: 14px; color: #1b7a6f; font-weight: 700;
  margin-bottom: 24px;
}
.pp-hero { text-align: center; padding: 40px 0 48px; }
.pp-hero h2 {
  font-size: 38px; font-weight: 900; line-height: 1.25;
  letter-spacing: -1.2px; margin-bottom: 16px;
}
.pp-hero h2 em { font-style: normal; color: #2A9D8F; }
.pp-hero p { font-size: 16px; color: #6c757d; line-height: 1.75; margin-bottom: 32px; }
.pp-cta {
  display: inline-block; background: #2A9D8F; color: #fff !important;
  padding: 16px 44px; border-radius: 14px; font-size: 17px; font-weight: 800;
  text-decoration: none !important; box-shadow: 0 8px 28px rgba(42,157,143,0.3);
  transition: all 0.2s; letter-spacing: -0.2px;
}
.pp-cta:hover { background: #1f8075; transform: translateY(-1px); box-shadow: 0 10px 32px rgba(42,157,143,0.4); }
.pp-hint { margin-top: 12px; font-size: 13px; color: #adb5bd; }

/* 3단계 */
.pp-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin: 0 0 56px; }
.pp-step { text-align: center; }
.pp-step-icon {
  width: 72px; height: 72px; border-radius: 50%; border: 3px solid #2A9D8F;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 16px; font-size: 32px; position: relative; background: var(--entry);
}
.pp-step-num {
  position: absolute; top: -6px; right: -6px;
  width: 24px; height: 24px; background: #2A9D8F; color: white;
  border-radius: 50%; font-size: 12px; font-weight: 800;
  display: flex; align-items: center; justify-content: center;
}
.pp-step-title { font-size: 16px; font-weight: 800; margin-bottom: 8px; }
.pp-step-desc { font-size: 14px; color: #6c757d; line-height: 1.7; }

/* 지원 사이트 */
.pp-sites { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 0 0 56px; }
.pp-site {
  background: var(--entry); border-radius: 14px; padding: 24px 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05); transition: box-shadow 0.2s;
}
.pp-site:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.1); }
.pp-site-icon { font-size: 32px; margin-bottom: 10px; }
.pp-site-name { font-size: 15px; font-weight: 800; margin-bottom: 6px; }
.pp-site-sub { font-size: 13px; color: #adb5bd; margin-bottom: 10px; }
.pp-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.pp-tag {
  background: #f0fdf9; color: #1b7a6f; border-radius: 6px;
  padding: 3px 8px; font-size: 11px; font-weight: 600;
}

/* 보안 안내 */
.pp-privacy {
  display: inline-flex; align-items: center; gap: 8px;
  background: #f0fdf9; border: 1px solid #b2e8e2; border-radius: 12px;
  padding: 14px 22px; font-size: 14px; color: #1b7a6f; margin-bottom: 28px;
}
.pp-footer { text-align: center; padding: 40px 0; }

@media (max-width: 700px) {
  .pp-hero h2 { font-size: 28px; }
  .pp-steps { grid-template-columns: 1fr; gap: 20px; }
  .pp-sites { grid-template-columns: 1fr; }
}
</style>

<div class="pp-welcome">

<section class="pp-hero">
  <div class="pp-badge">🎉 설치해주셔서 감사합니다!</div>
  <h2>공공기관 간편인증,<br>이제 <em>자동으로</em> 됩니다</h2>
  <p>홈택스·정부24·건강보험공단에서 매번 이름·생년월일·번호를 직접 입력하셨나요?<br>한 번만 등록하면 PassPass가 대신 채워드립니다.</p>
  <div class="pp-hint">🔧 브라우저 우측 상단 <strong>PassPass 아이콘</strong>을 클릭해서 정보를 등록하세요</div>
</section>

---

## 이렇게 사용하세요

<div class="pp-steps">
  <div class="pp-step">
    <div class="pp-step-icon">
      <span class="pp-step-num">1</span>
      📝
    </div>
    <div class="pp-step-title">정보 한 번 등록</div>
    <div class="pp-step-desc">이름·생년월일·번호·인증기관을 PassPass에 저장합니다. 숫자 4자리 PIN으로 안전하게 보호됩니다.</div>
  </div>
  <div class="pp-step">
    <div class="pp-step-icon">
      <span class="pp-step-num">2</span>
      🌐
    </div>
    <div class="pp-step-title">지원 사이트 방문</div>
    <div class="pp-step-desc">홈택스·정부24·건강보험공단 등 지원 사이트에 접속하고 간편인증을 시작합니다.</div>
  </div>
  <div class="pp-step">
    <div class="pp-step-icon">
      <span class="pp-step-num">3</span>
      ⚡
    </div>
    <div class="pp-step-title">자동으로 입력 완료!</div>
    <div class="pp-step-desc">팝업이 열리는 순간 PassPass가 자동으로 채웁니다. 이제 인증 버튼만 누르면 끝입니다.</div>
  </div>
</div>

---

## 지원 사이트

<div class="pp-sites">
  <div class="pp-site">
    <div class="pp-site-icon">🏛️</div>
    <div class="pp-site-name">공공기관</div>
    <div class="pp-site-sub">간편인증 자동입력</div>
    <div class="pp-tags">
      <span class="pp-tag">홈택스</span>
      <span class="pp-tag">정부24</span>
      <span class="pp-tag">건강보험</span>
      <span class="pp-tag">고용보험</span>
      <span class="pp-tag">국민연금</span>
      <span class="pp-tag">코레일</span>
    </div>
  </div>
  <div class="pp-site">
    <div class="pp-site-icon">🚗</div>
    <div class="pp-site-name">다이렉트 보험</div>
    <div class="pp-site-sub">견적 폼 자동입력</div>
    <div class="pp-tags">
      <span class="pp-tag">삼성화재</span>
      <span class="pp-tag">현대해상</span>
      <span class="pp-tag">DB손보</span>
      <span class="pp-tag">KB손보</span>
      <span class="pp-tag">메리츠</span>
      <span class="pp-tag">한화·하나·롯데</span>
    </div>
  </div>
  <div class="pp-site">
    <div class="pp-site-icon">🛒</div>
    <div class="pp-site-name">쿠팡</div>
    <div class="pp-site-sub">로그인 자동화</div>
    <div class="pp-tags">
      <span class="pp-tag">이메일 로그인</span>
      <span class="pp-tag">휴대폰 로그인</span>
      <span class="pp-tag">QR 로그인</span>
    </div>
  </div>
  <div class="pp-site">
    <div class="pp-site-icon">🔑</div>
    <div class="pp-site-name">네이버 · 카카오</div>
    <div class="pp-site-sub">로그인 자동화</div>
    <div class="pp-tags">
      <span class="pp-tag">네이버 ID</span>
      <span class="pp-tag">일회용번호</span>
      <span class="pp-tag">카카오 QR</span>
    </div>
  </div>
</div>

---

<div class="pp-footer">
  <div class="pp-privacy">
    🔒 모든 정보는 <strong>&nbsp;내 브라우저에만 저장</strong>됩니다. 외부 서버로 전송되지 않습니다.
  </div>
  <br><br>
  <div class="pp-hint">우측 상단 PassPass 아이콘을 클릭해서 언제든 정보를 등록하거나 수정할 수 있습니다</div>
</div>

</div>
