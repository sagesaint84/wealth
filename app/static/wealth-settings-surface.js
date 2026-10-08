/* Settings markup only. Layout creates it directly in its final page; no dialog or reparenting. */
(() => {
  'use strict';
  window.WealthSettingsSurfaceMarkup = () => `<div id="settingsSurface" class="settings-surface">
  <div id="settingsTabs" class="wealth-section-tabs settings-tabs" role="tablist" aria-label="설정 분류">
    <button id="settingsApiTab" type="button" role="tab" aria-selected="true" aria-controls="settingsApiPanel" data-settings-tab="api" tabindex="0">API 연결</button>
    <button id="settingsNotificationsTab" type="button" role="tab" aria-selected="false" aria-controls="settingsNotificationsPanel" data-settings-tab="notifications" tabindex="-1">알림 · 자동화</button>
  </div>
  <section id="settingsApiPanel" role="tabpanel" aria-labelledby="settingsApiTab" data-settings-panel="api">
    <p id="settingsApiLoading" class="settings-loading" role="status" hidden>연결 설정을 불러오는 중…</p>
    <p id="settingsApiError" class="settings-error" role="alert" hidden></p>
    <button type="button" class="button secondary compact settings-retry" data-settings-retry="api" hidden>연결 설정 다시 불러오기</button>
    <fieldset id="settingsApiFields" class="settings-panel-fields" disabled>
      <h3 class="settings-group-title">증권사 OpenAPI</h3>
    <p class="settings-help">각 증권사에서 발급받은 인증정보를 등록합니다. 저장된 비밀정보는 다시 표시하지 않습니다.</p>
    <form id="userOpenApiForm" onsubmit="handleSaveUserOpenApi(event)">
      <div class="settings-api-grid"><div class="openapi-broker-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:700;color:#60a5fa;font-size:13.5px;display:flex;align-items:center;gap:6px;">
              🟦 토스증권 (Toss)
            </span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiTossBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiTossDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteBrokerApi('toss')" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="토스증권 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <div class="settings-api-fields">
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiTossKey">Client ID (App Key)</label>
              <input id="openapiTossKey" class="openapi-input" type="text" placeholder="Client ID 입력" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiTossSecret">Client Secret</label>
              <input id="openapiTossSecret" class="openapi-input" type="password" placeholder="Client Secret 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
          </div>
        </div><div class="openapi-broker-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:700;color:#facc15;font-size:13.5px;display:flex;align-items:center;gap:6px;">
              🟨 KB증권
            </span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiKbBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiKbDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteBrokerApi('kb')" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="KB증권 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <div class="settings-api-fields">
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKbKey">App Key</label>
              <input id="openapiKbKey" class="openapi-input" type="text" placeholder="KB App Key 입력" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKbSecret">App Secret</label>
              <input id="openapiKbSecret" class="openapi-input" type="password" placeholder="KB App Secret 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
          </div>
          <div>
            <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKbAccountNo">KB증권 계좌번호 (11자리)</label>
            <input id="openapiKbAccountNo" class="openapi-input" type="text" placeholder="하이픈 없이 11자리 계좌번호를 입력하세요." autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            <div style="font-size:11px;color:#94a3b8;margin-top:4px;">하이픈 없이 11자리 계좌번호를 입력하세요.</div>
          </div>
        </div><div class="openapi-broker-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:700;color:#4ade80;font-size:13.5px;display:flex;align-items:center;gap:6px;">
              🟩 NH투자증권 (나무)
            </span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiNhBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiNhDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteBrokerApi('nh')" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="나무증권 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <div class="settings-api-fields">
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiNhKey">App Key</label>
              <input id="openapiNhKey" class="openapi-input" type="text" placeholder="나무 App Key 입력" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiNhSecret">App Secret</label>
              <input id="openapiNhSecret" class="openapi-input" type="password" placeholder="나무 App Secret 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
          </div>
        </div><div class="openapi-broker-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:700;color:#f97316;font-size:13.5px;display:flex;align-items:center;gap:6px;">
              🟧 한국투자증권 (KIS)
            </span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiKisBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiKisDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteBrokerApi('kis')" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="한국투자증권 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <div class="settings-api-fields">
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKisKey">App Key</label>
              <input id="openapiKisKey" class="openapi-input" type="text" placeholder="한투 App Key 입력" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKisSecret">App Secret</label>
              <input id="openapiKisSecret" class="openapi-input" type="password" placeholder="한투 App Secret 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
          </div>
          <div>
            <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKisAccountNo">계좌번호 (CANO 8자리 또는 8자리-01)</label>
            <input id="openapiKisAccountNo" class="openapi-input" type="text" placeholder="예: 12345678-01 또는 12345678" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
          </div>
        </div><div class="openapi-broker-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:700;color:#c084fc;font-size:13.5px;display:flex;align-items:center;gap:6px;">
              🟪 키움증권 (Kiwoom)
            </span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiKiwoomBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiKiwoomDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteBrokerApi('kiwoom')" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="키움증권 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <div class="settings-api-fields">
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKiwoomKey">App Key</label>
              <input id="openapiKiwoomKey" class="openapi-input" type="text" placeholder="키움 App Key 입력" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
            <div>
              <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKiwoomSecret">App Secret</label>
              <input id="openapiKiwoomSecret" class="openapi-input" type="password" placeholder="키움 App Secret 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
            </div>
          </div>
          <div>
            <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiKiwoomAccountNo">계좌번호 (선택 · API에서 자동 조회)</label>
            <input id="openapiKiwoomAccountNo" class="openapi-input" type="text" placeholder="입력하지 않아도 됩니다" autocomplete="off" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
          </div>
        </div></div>
      <p class="settings-help">등록된 인증키는 마스킹되어 표시됩니다. 빈 비밀정보·계좌 입력은 기존 저장값을 유지하며, 삭제 버튼으로만 연결을 해제합니다.</p>
      <div id="openapiStatusMsg" class="settings-error" role="alert" style="display:none;"></div>
      <div class="settings-actions"><button id="saveUserOpenApiBtn" class="button primary" type="submit">💾 설정 저장</button></div>
    </form>
    <h3 class="settings-group-title">데이터 소스</h3>
    <div class="settings-api-grid"><section id="openapiKrxSection" class="openapi-broker-card" style="margin-top:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div><strong>🏛️ KRX Data Marketplace</strong><div class="muted" style="font-size:11px;margin-top:3px;">과거 공모주 전체 조회 전용 로그인 · 사용자별 secrets에 저장</div></div>
          <span id="openapiKrxBadge" class="openapi-badge disconnected">미설정</span>
        </div>
        <div class="form-grid" style="margin-top:10px;">
          <label>아이디 <input id="openapiKrxLoginId" type="text" autocomplete="off" placeholder="KRX 아이디" /></label>
          <label>비밀번호 <input id="openapiKrxPassword" type="password" autocomplete="new-password" placeholder="저장된 비밀번호는 표시하지 않음" /></label>
        </div>
        <div id="openapiKrxMessage" class="muted" style="font-size:11px;margin-top:8px;"></div>
        <div class="settings-actions" style="margin-top:10px;justify-content:flex-start;">
          <button type="button" class="button primary compact" onclick="saveKrxMarketplaceConfig()">저장</button>
          <button type="button" class="button secondary compact" onclick="testKrxMarketplaceConfig()">연결 확인</button>
          <button type="button" id="openapiKrxDeleteBtn" class="button secondary compact" onclick="deleteKrxMarketplaceConfig()" style="display:none;">삭제</button>
        </div>
      </section><section id="openapiDartSection" class="openapi-broker-card" aria-labelledby="openapiDartTitle">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span id="openapiDartTitle" style="font-weight:700;color:#fbbf24;font-size:13.5px;display:flex;align-items:center;gap:6px;">📊 시장 데이터 API · OpenDART</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span id="openapiDartBadge" class="openapi-badge disconnected">확인 중...</span>
              <button id="openapiDartDeleteBtn" type="button" class="button secondary compact" onclick="handleDeleteDartApi()" style="display:none;font-size:11px;padding:2px 7px;border-radius:6px;color:#ff718c;border:1px solid rgba(255,113,140,0.3);background:rgba(255,113,140,0.08);cursor:pointer;" title="OpenDART 연결 삭제">🗑️ 삭제</button>
            </div>
          </div>
          <p style="font-size:11.5px;line-height:1.5;margin:0 0 9px;color:var(--muted,#94a3b8);">공모주 증권신고서 분석 및 의무보유확약·기관경쟁률 수집에 사용됩니다. 저장된 키는 다시 표시되지 않습니다.</p>
          <label class="openapi-label" style="display:block;margin-bottom:4px;" for="openapiDartKey">DART API Key</label>
          <input id="openapiDartKey" class="openapi-input" type="password" placeholder="40자리 OpenDART 인증키 입력" autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:7px 10px;border-radius:6px;font-size:12.5px;" />
          <div style="display:flex;justify-content:flex-end;gap:6px;margin-top:9px;">
            <button id="openapiDartTestBtn" type="button" class="button secondary compact" onclick="handleTestDartApi()">연결 확인</button>
            <button id="openapiDartSaveBtn" type="button" class="button primary compact" onclick="handleSaveDartApi()">저장/교체</button>
          </div>
        </section></div>
    <h3 class="settings-group-title">데스크톱 / 실행 연동</h3><div id="settingsTossSessionSection" class="settings-section" aria-labelledby="tossSessionTitle">
            <h4 id="tossSessionTitle">내 Toss WTS 연결</h4>
            <p class="settings-help">남은 세션 시간이 기준값 이내이면 Wealth가 Toss 세션 연장을 요청합니다. Toss 모바일 앱 승인이 필요할 수 있습니다.</p>
            <div class="settings-status-grid">
              <div><strong>설정 / 예상 버전</strong><span id="settingsTossConfigured">확인 중</span></div>
              <div><strong>세션 파일</strong><span id="settingsTossSessionPresent">확인 중</span></div>
              <div><strong>실시간 세션</strong><span id="settingsTossLiveStatus">확인하지 않음</span></div>
              <div><strong>서버 만료 / 남은 시간</strong><span id="settingsTossExpiry">확인하지 않음</span></div>
              <div><strong>마지막 상태 확인</strong><span id="settingsTossCheckedAt">확인하지 않음</span></div>
            </div>
            <div class="settings-fields">
              <label><input id="settingsTossSessionEnabled" type="checkbox"> 세션 자동 점검</label>
            </div>
            <div class="settings-management-actions">
              <button id="settingsCheckTossSession" type="button" class="button secondary compact">세션 상태 확인</button>
              <button id="settingsSaveTossSession" type="button" class="button secondary compact">Toss 세션 설정 저장</button>
            </div>
            <div id="settingsTossLoginSection" class="settings-subsection">
              <h5>초기 인증 / 재인증 (QR)</h5>
              <p class="settings-help">세션이 없거나 만료된 경우 내 Toss WTS 계정을 QR 코드로 인증하거나 재인증할 수 있습니다.</p>
              <div id="settingsTossLoginQrArea" hidden>
                <img id="settingsTossLoginQr" src="" alt="Toss WTS QR 코드" style="max-width:220px;display:block;margin:8px 0;">
                <p id="settingsTossLoginStatus" class="settings-help" aria-live="polite"></p>
              </div>
              <div class="settings-management-actions">
                <button id="settingsTossLoginStart" type="button" class="button secondary compact">인증 시작 (QR 발급)</button>
                <button id="settingsTossLoginCancel" type="button" class="button secondary compact" hidden>취소</button>
              </div>
            </div>
          <p id="settingsTossError" class="settings-error" role="alert" hidden></p></div>
  </fieldset>
      </section>
  <section id="settingsNotificationsPanel" role="tabpanel" aria-labelledby="settingsNotificationsTab" data-settings-panel="notifications" hidden>
    <p class="settings-help">Telegram·Discord·카카오 알림과 Wealth 자동 실행 시간을 관리합니다.</p>
    <p id="settingsLoading" class="settings-loading" role="status" hidden>설정을 불러오는 중…</p>
    <p id="settingsNotificationsError" class="settings-error" role="alert" hidden></p>
    <button type="button" class="button secondary compact settings-retry" data-settings-retry="notifications" hidden>알림 설정 다시 불러오기</button><fieldset id="settingsNotificationsFields" class="settings-panel-fields" disabled>
      <div id="settingsContent" class="settings-content">
        <section class="settings-section" aria-labelledby="telegramSettingsTitle">
          <div class="settings-section-title">
            <div><h3 id="telegramSettingsTitle">Telegram 알림</h3><p>설정 여부만 표시하며 실제 연결 상태는 확인하지 않습니다.</p></div>
            <label class="settings-switch"><input id="settingsTelegramEnabled" type="checkbox"><span>사용</span></label>
          </div>
          <div class="settings-secret-grid">
            <div class="settings-secret-card">
              <div><strong>Bot Token</strong><span id="settingsBotStatus" class="settings-source">미설정</span></div>
              <input id="settingsBotToken" type="password" autocomplete="new-password" placeholder="변경할 때만 새 값을 입력하세요" aria-label="새 Telegram Bot Token">
              <button id="settingsClearBot" type="button" class="button secondary compact settings-clear">저장된 값 삭제</button>
            </div>
            <div class="settings-secret-card">
              <div><strong>Webhook Secret</strong><span id="settingsWebhookStatus" class="settings-source">미설정</span></div>
              <input id="settingsWebhookSecret" type="password" autocomplete="new-password" placeholder="변경할 때만 새 값을 입력하세요" aria-label="새 Telegram Webhook Secret">
              <button id="settingsClearWebhook" type="button" class="button secondary compact settings-clear">저장된 값 삭제</button>
            </div>
          </div>
          <div class="settings-fields">
            <label>Chat ID<input id="settingsChatId" type="text" inputmode="numeric" autocomplete="off"></label>
            <label>Allowed User ID<input id="settingsAllowedUserId" type="text" inputmode="numeric" autocomplete="off"></label>
            <label>Allowed Chat ID<input id="settingsAllowedChatId" type="text" inputmode="numeric" autocomplete="off"></label>
          </div>
          <div class="settings-management" aria-labelledby="telegramManagementTitle">
            <h4 id="telegramManagementTitle">Telegram 관리</h4>
            <label>Public URL<input id="settingsPublicBaseUrl" type="url" autocomplete="url" placeholder="https://wealth.example.com"></label>
            <p id="settingsPublicUrlSource" class="settings-source">미설정</p>
            <div class="settings-management-actions">
              <button id="settingsSaveSystem" type="button" class="button secondary compact">Public URL 저장 · 현재 사용자 연결</button>
              <button id="settingsCheckTelegram" type="button" class="button secondary compact">Telegram 상태 확인</button>
              <button id="settingsSendTest" type="button" class="button secondary compact">테스트 메시지 보내기</button>
            </div>
            <div class="settings-status-grid">
              <div><strong>Bot 상태</strong><span id="settingsBotApiStatus">확인하지 않음</span></div>
              <div><strong>Webhook 상태</strong><span id="settingsWebhookApiStatus">확인하지 않음</span></div>
            </div>
            <div id="settingsWebhookDetails" class="settings-webhook-details" hidden>
              <span>URL</span><strong id="settingsWebhookUrl"></strong>
              <span>대기 업데이트</span><strong id="settingsPendingUpdates">0</strong>
              <span>최근 오류</span><strong id="settingsWebhookLastError">없음</strong>
            </div>
            <div class="settings-management-actions">
              <button id="settingsConnectWebhook" type="button" class="button primary compact">Webhook 연결</button>
              <button id="settingsDisconnectWebhook" type="button" class="button secondary compact">Webhook 연결 해제</button>
            </div>
          </div>
          <p id="settingsTelegramError" class="settings-error" role="alert" hidden></p>
          <div class="settings-actions"><button id="settingsSaveTelegram" type="button" class="button primary">Telegram 설정 저장</button></div>
        </section>

        <section class="settings-section" aria-labelledby="discordSettingsTitle">
          <div class="settings-section-title">
            <div>
              <h3 id="discordSettingsTitle">Discord 알림</h3>
              <p>현재 Wealth 사용자 전용 Discord Webhook을 저장하고 테스트합니다.</p>
            </div>
            <label class="settings-switch"><input id="settingsDiscordEnabled" type="checkbox"><span>사용</span></label>
          </div>
          <div class="settings-secret-grid">
            <div class="settings-secret-card">
              <div><strong>Webhook URL</strong><span id="settingsDiscordWebhookStatus" class="settings-source">미설정</span></div>
              <input id="settingsDiscordWebhookUrl" type="password" autocomplete="new-password" placeholder="변경할 때만 새 값을 입력하세요" aria-label="새 Discord Webhook URL">
              <button id="settingsClearDiscordWebhook" type="button" class="button secondary compact settings-clear">저장된 값 삭제</button>
            </div>
          </div>
          <div class="settings-management-actions">
            <button id="settingsDiscordTest" type="button" class="button secondary compact">테스트 메시지 보내기</button>
          </div>
          <p id="settingsDiscordError" class="settings-error" role="alert" hidden></p>
          <div class="settings-actions"><button id="settingsSaveDiscord" type="button" class="button primary">Discord 설정 저장</button></div>
        </section>

        <section class="settings-section" aria-labelledby="kakaoSettingsTitle">
          <div class="settings-section-title">
            <div>
              <h3 id="kakaoSettingsTitle">카카오톡 나에게 보내기</h3>
              <p>카카오 로그인으로 현재 Wealth 사용자와 본인의 카카오톡을 연결합니다.</p>
            </div>
            <label class="settings-switch"><input id="settingsKakaoEnabled" type="checkbox"><span>사용</span></label>
          </div>
          <div class="settings-secret-grid">
            <div class="settings-secret-card">
              <div><strong>REST API Key</strong><span id="settingsKakaoRestApiKeyStatus" class="settings-source">미설정</span></div>
              <input id="settingsKakaoRestApiKey" type="password" autocomplete="new-password" placeholder="변경할 때만 새 값을 입력하세요" aria-label="새 Kakao REST API Key">
              <button id="settingsClearKakaoRestApiKey" type="button" class="button secondary compact settings-clear">저장된 값 삭제</button>
            </div>
            <div class="settings-secret-card">
              <div><strong>Client Secret</strong><span id="settingsKakaoClientSecretStatus" class="settings-source">미설정</span></div>
              <input id="settingsKakaoClientSecret" type="password" autocomplete="new-password" placeholder="변경할 때만 새 값을 입력하세요" aria-label="새 Kakao Client Secret">
              <button id="settingsClearKakaoClientSecret" type="button" class="button secondary compact settings-clear">저장된 값 삭제</button>
            </div>
          </div>
          <div class="settings-status-grid">
            <div><strong>카카오 앱 설정</strong><span id="settingsKakaoAppStatus">확인 중</span></div>
            <div><strong>내 계정 연결</strong><span id="settingsKakaoConnectionStatus">확인 중</span></div>
            <div><strong>Access Token 만료</strong><span id="settingsKakaoAccessExpiry">없음</span></div>
            <div><strong>Refresh Token 만료</strong><span id="settingsKakaoRefreshExpiry">없음</span></div>
          </div>
          <div class="settings-management">
            <h4>OAuth 설정</h4>
            <p class="settings-help">Kakao Developers에 아래 Redirect URI를 등록하고, 카카오 로그인·카카오톡 메시지 전송(talk_message) 동의항목을 활성화하며, Wealth Public URL 도메인을 제품 링크의 웹 도메인으로 등록해야 합니다.</p>
            <div class="settings-webhook-details">
              <span>Redirect URI</span><strong id="settingsKakaoRedirectUri">Public URL 설정 필요</strong>
            </div>
            <div class="settings-management-actions">
              <button id="settingsKakaoConnect" type="button" class="button primary compact">카카오 연결</button>
              <button id="settingsKakaoTest" type="button" class="button secondary compact">나에게 테스트 보내기</button>
              <button id="settingsKakaoDisconnect" type="button" class="button secondary compact">연결 정보 삭제</button>
            </div>
          </div>
          <p id="settingsKakaoError" class="settings-error" role="alert" hidden></p>
          <div class="settings-actions"><button id="settingsSaveKakaoSecrets" type="button" class="button primary">Kakao 앱 키 저장</button></div>
        </section>

        <section class="settings-section" aria-labelledby="notificationHistoryTitle">
          <div class="settings-section-title">
            <div>
              <h3 id="notificationHistoryTitle">최근 알림 전송</h3>
              <p>최근 최대 100건의 이벤트 종류와 provider별 성공·실패만 저장합니다. 메시지 본문과 비밀정보는 저장하지 않습니다.</p>
            </div>
            <div class="settings-management-actions settings-history-actions">
              <button id="settingsNotificationHistoryRefresh" type="button" class="button secondary compact">새로고침</button>
              <button id="settingsNotificationHistoryClear" type="button" class="button secondary compact">이력 비우기</button>
            </div>
          </div>
          <p id="settingsNotificationHistorySummary" class="settings-history-summary">최근 이력을 불러오는 중…</p>
          <div id="settingsNotificationHistoryList" class="settings-history-list" aria-live="polite"></div>
          <p id="settingsNotificationHistoryError" class="settings-error" role="alert" hidden></p>
        </section>

        <section class="settings-section" aria-labelledby="automationSettingsTitle">
          <div class="settings-section-title"><div><h3 id="automationSettingsTitle">자동화</h3><p>시간대: <strong id="settingsTimezone">Asia/Seoul</strong></p></div></div>
          <div class="settings-task"><label><input id="settingsMorningEnabled" type="checkbox"> IPO 오전 갱신</label><input id="settingsMorningTime" class="settings-time" type="text" inputmode="numeric" placeholder="07:30" aria-label="IPO 오전 갱신 시간"></div>
          <div class="settings-task settings-reminders"><label><input id="settingsRemindersEnabled" type="checkbox"> 공모주 청약 알림</label><div><div id="settingsReminderTimes" class="settings-reminder-list"></div><button id="settingsAddReminder" type="button" class="button secondary compact">+ 알림 시간 추가</button></div></div>
          <div class="settings-task settings-reminders"><label><input id="settingsListingRemindersEnabled" type="checkbox"> 공모주 상장일 알림</label><div><div id="settingsListingReminderTimes" class="settings-reminder-list"></div><button id="settingsAddListingReminder" type="button" class="button secondary compact">+ 알림 시간 추가</button></div></div>
          <div class="settings-task"><label><input id="settingsEveningEnabled" type="checkbox"> IPO 장후 갱신</label><input id="settingsEveningTime" class="settings-time" type="text" inputmode="numeric" placeholder="18:30" aria-label="IPO 장후 갱신 시간"></div>
          <div class="settings-task"><label><input id="settingsDailyCloseEnabled" type="checkbox"> 일일 마감</label><input id="settingsDailyCloseTime" class="settings-time" type="text" inputmode="numeric" placeholder="21:00" aria-label="일일 마감 시간"></div>
          <div id="settingsAutomationStatusPanel" class="automation-status-panel">
            <div class="automation-status-head"><div><h4>자동화 실행 상태</h4><p>최근 실행 결과와 다음 예정 시간을 표시합니다. 원문 오류·비밀정보는 표시하지 않습니다.</p></div>
              <button id="settingsAutomationStatusRefresh" type="button" class="button secondary compact">새로고침</button></div>
            <div id="settingsAutomationStatusSummary" class="automation-status-summary"></div>
            <div id="settingsAutomationStatusGrid" class="automation-status-grid"></div>
            <details class="automation-status-recent"><summary>최근 실행 기록</summary><div id="settingsAutomationStatusRecent" class="automation-status-recent-list"></div></details>
            <p id="settingsAutomationStatusError" class="settings-error" role="alert" hidden></p>
          </div>
          <div id="settingsAutomationOwnerSection" class="settings-management" aria-labelledby="automationOwnerTitle" hidden>
            <h4 id="automationOwnerTitle">전역 자동화 실행 사용자</h4>
            <p class="settings-help">IPO 시장 갱신처럼 전체 Wealth에서 한 번만 실행되는 자동화의 기준 사용자를 지정합니다.</p>
            <div class="settings-status-grid">
              <div><strong>현재 실행 사용자</strong><span id="settingsAutomationOwnerName">미설정</span></div>
              <div><strong>설정 출처</strong><span id="settingsAutomationOwnerSource">없음</span></div>
            </div>
            <div class="settings-management-actions">
              <button id="settingsSetAutomationOwner" type="button" class="button secondary compact">현재 사용자를 실행 사용자로 지정</button>
              <button id="settingsClearAutomationOwner" type="button" class="button secondary compact">전역 자동화 사용자 해제</button>
            </div>
          </div>

          <p id="settingsAutomationError" class="settings-error" role="alert" hidden></p>
          <div class="settings-actions"><button id="settingsSaveAutomation" type="button" class="button primary">자동화 설정 저장</button></div>
        </section>
      </div>
  </fieldset>
      </section>
</div>`;
})();
