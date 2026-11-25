(() => {
  "use strict";

  function create({ window, document, getDaysInMonth }) {
    function setupAutoAdvancingDateInput(wrapSelector) {
      const wrap = typeof wrapSelector === "string" ? document.querySelector(wrapSelector) : wrapSelector;
      if (!wrap || wrap.dataset.autoAdvancingInit === "true") return;
      wrap.dataset.autoAdvancingInit = "true";

      const yearInput = wrap.querySelector(".date-part-year");
      const monthInput = wrap.querySelector(".date-part-month");
      const dayInput = wrap.querySelector(".date-part-day");
      const triggerBtn = wrap.querySelector(".date-picker-trigger");
      const nativeInput = wrap.querySelector("input[type='date']");

      if (!yearInput || !monthInput || !dayInput || !nativeInput) return;

      const origValDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
      let isSyncingToNative = false;

      function syncToNative() {
        const y = (yearInput.value || "").trim();
        const m = (monthInput.value || "").trim();
        const d = (dayInput.value || "").trim();
        // 연도 4자리, 월 2자리, 일 2자리가 모두 완전하게 입력되었을 때만 네이티브로 동기화
        // (타이핑 도중 1자리 미완성 상태에서 padStart로 덮어씌워지는 순환 오류 원천 방지)
        if (y.length === 4 && m.length === 2 && d.length === 2) {
          const iso = `${y}-${m}-${d}`;
          isSyncingToNative = true;
          try {
            if (origValDesc) {
              origValDesc.set.call(nativeInput, iso);
            } else {
              nativeInput.value = iso;
            }
            nativeInput.dispatchEvent(new Event("input", { bubbles: true }));
            nativeInput.dispatchEvent(new Event("change", { bubbles: true }));
          } finally {
            isSyncingToNative = false;
          }
        }
      }

      function syncFromNative() {
        if (isSyncingToNative) return;
        const val = origValDesc ? origValDesc.get.call(nativeInput) : nativeInput.value;
        if (val && /^\d{4}-\d{2}-\d{2}$/.test(val)) {
          const [y, m, d] = val.split("-");
          yearInput.value = y;
          monthInput.value = m;
          dayInput.value = d;
        }
      }

      // nativeInput.value 프로퍼티 가로채기를 통해 프로그래밍 방식 값 변경 시에도 분할 입력칸 즉시 동기화
      if (origValDesc) {
        try {
          Object.defineProperty(nativeInput, "value", {
            get() {
              return origValDesc.get.call(this);
            },
            set(newVal) {
              origValDesc.set.call(this, newVal);
              if (!isSyncingToNative) {
                syncFromNative();
              }
            },
            configurable: true
          });
        } catch (e) {
          console.warn("Could not define property on native date input", e);
        }
      }

      function tryDistributeDateString(str) {
        if (!str) return false;
        const clean = str.trim();
        const m = clean.match(/^(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})$/);
        if (m) {
          yearInput.value = m[1];
          monthInput.value = m[2].padStart(2, "0");
          dayInput.value = m[3].padStart(2, "0");
          syncToNative();
          dayInput.focus();
          return true;
        }
        return false;
      }

      // 래퍼 영역 클릭 시 빈 칸 또는 연도로 스마트 포커스
      wrap.addEventListener("click", (e) => {
        if (e.target === wrap || e.target.classList.contains("date-part-sep")) {
          if (!yearInput.value) {
            yearInput.focus();
          } else if (!monthInput.value) {
            monthInput.focus();
          } else if (!dayInput.value) {
            dayInput.focus();
          } else {
            yearInput.focus();
            yearInput.select();
          }
        }
      });

      // 포커스 시 전체 선택 (빠른 재입력 편의성)
      yearInput.addEventListener("focus", () => yearInput.select());
      monthInput.addEventListener("focus", () => monthInput.select());
      dayInput.addEventListener("focus", () => dayInput.select());

      // [핵심] 연도(Year): 4자리 숫자 입력 시 자동으로 월(Month) 입력칸으로 이동
      yearInput.addEventListener("input", () => {
        const raw = yearInput.value.replace(/\D/g, "");
        if (raw.length > 4) {
          if (tryDistributeDateString(raw)) return;
          yearInput.value = raw.slice(0, 4);
        } else {
          yearInput.value = raw;
        }
        if (yearInput.value.length === 4) {
          syncToNative();
          monthInput.focus();
          monthInput.select();
        }
      });

      yearInput.addEventListener("blur", () => {
        let raw = yearInput.value.replace(/\D/g, "");
        if (raw.length === 2) {
          yearInput.value = String(2000 + parseInt(raw, 10));
          syncToNative();
        }
      });

      yearInput.addEventListener("keydown", (e) => {
        if (["ArrowRight", "Enter", "/", "-", "."].includes(e.key)) {
          if (yearInput.value.length >= 2) {
            if (yearInput.value.length === 2) {
              yearInput.value = String(2000 + parseInt(yearInput.value, 10));
              syncToNative();
            }
            e.preventDefault();
            monthInput.focus();
            monthInput.select();
          }
        }
      });

      yearInput.addEventListener("paste", (e) => {
        const pasted = (e.clipboardData || window.clipboardData)?.getData("text");
        if (pasted && tryDistributeDateString(pasted)) {
          e.preventDefault();
        }
      });

      // 월(Month): 2자리 입력 시(또는 2~9 한자리 입력 시 0 자동 패딩) 자동으로 일(Day) 입력칸으로 이동
      monthInput.addEventListener("input", () => {
        let raw = monthInput.value.replace(/\D/g, "").slice(0, 2);
        // 2~9 입력 시 02~09로 자동 완성 후 바로 일(day)로 이동
        if (raw.length === 1 && parseInt(raw, 10) >= 2) {
          raw = "0" + raw;
          monthInput.value = raw;
          syncToNative();
          dayInput.focus();
          dayInput.select();
          return;
        }
        monthInput.value = raw;
        // 0 또는 1 입력 시에는 두 번째 자리 입력을 위해 즉시 sync하지 않고 대기
        if (raw.length === 2) {
          let num = parseInt(raw, 10);
          if (num > 12) num = 12;
          if (num < 1) num = 1;
          monthInput.value = String(num).padStart(2, "0");
          syncToNative();
          dayInput.focus();
          dayInput.select();
        }
      });

      monthInput.addEventListener("blur", () => {
        let raw = monthInput.value.replace(/\D/g, "");
        if (raw.length === 1) {
          let num = parseInt(raw, 10);
          if (num >= 1 && num <= 12) {
            monthInput.value = String(num).padStart(2, "0");
            syncToNative();
          }
        }
      });

      monthInput.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !monthInput.value) {
          e.preventDefault();
          yearInput.focus();
          yearInput.setSelectionRange(yearInput.value.length, yearInput.value.length);
        } else if (e.key === "ArrowLeft" && monthInput.selectionStart === 0) {
          e.preventDefault();
          yearInput.focus();
          yearInput.setSelectionRange(yearInput.value.length, yearInput.value.length);
        } else if (["ArrowRight", "Enter", "/", "-", "."].includes(e.key)) {
          if (monthInput.value.length >= 1) {
            if (monthInput.value.length === 1) {
              monthInput.value = monthInput.value.padStart(2, "0");
              syncToNative();
            }
            e.preventDefault();
            dayInput.focus();
            dayInput.select();
          }
        }
      });

      // 일(Day): 2자리 입력 시 유효 범위 보정 및 동기화
      dayInput.addEventListener("input", () => {
        let raw = dayInput.value.replace(/\D/g, "").slice(0, 2);
        // 4~9는 어떤 월에도 10자리 수가 될 수 없으므로(31일까지 존재) 04~09로 즉시 패딩
        if (raw.length === 1 && parseInt(raw, 10) >= 4) {
          raw = "0" + raw;
          dayInput.value = raw;
          syncToNative();
          return;
        }
        dayInput.value = raw;
        // 0, 1, 2, 3 입력 시에는 10~31 등 두 번째 자리(예: 25일) 입력을 온전히 받기 위해 대기
        if (raw.length === 2) {
          let num = parseInt(raw, 10);
          const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
          const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
          const maxDays = getDaysInMonth(y, m);
          if (num > maxDays) num = maxDays;
          if (num < 1) num = 1;
          dayInput.value = String(num).padStart(2, "0");
          syncToNative();
        }
      });

      dayInput.addEventListener("blur", () => {
        let raw = dayInput.value.replace(/\D/g, "");
        if (raw.length === 1) {
          let num = parseInt(raw, 10);
          if (num >= 1 && num <= 31) {
            dayInput.value = String(num).padStart(2, "0");
            syncToNative();
          }
        }
      });

      dayInput.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !dayInput.value) {
          e.preventDefault();
          monthInput.focus();
          monthInput.setSelectionRange(monthInput.value.length, monthInput.value.length);
        } else if (e.key === "ArrowLeft" && dayInput.selectionStart === 0) {
          e.preventDefault();
          monthInput.focus();
          monthInput.setSelectionRange(monthInput.value.length, monthInput.value.length);
        } else if (e.key === "Enter") {
          let raw = dayInput.value.replace(/\D/g, "");
          if (raw.length === 1) {
            let num = parseInt(raw, 10);
            if (num >= 1 && num <= 31) {
              dayInput.value = String(num).padStart(2, "0");
              syncToNative();
            }
          }
        }
      });

      // 마우스오버 툴팁 안내 (미설정 시 기본 주입)
      if (!yearInput.getAttribute("title")) yearInput.setAttribute("title", "마우스 휠로 연도 조절 가능");
      if (!monthInput.getAttribute("title")) monthInput.setAttribute("title", "마우스 휠로 월 조절 가능");
      if (!dayInput.getAttribute("title")) dayInput.setAttribute("title", "마우스 휠로 일 조절 가능");

      // [핵심] 마우스오버 상태에서 휠 회전 시 연도/월/일 실시간 증감 (모달/페이지 스크롤 방지: passive: false)
      yearInput.addEventListener("wheel", (e) => {
        e.preventDefault();
        let y = parseInt(yearInput.value, 10);
        if (isNaN(y) || y < 1900 || y > 2100) {
          y = new Date().getFullYear();
        }
        const step = e.deltaY < 0 ? 1 : -1;
        y = Math.min(2100, Math.max(1900, y + step));
        yearInput.value = String(y);

        if (!monthInput.value) {
          monthInput.value = String(new Date().getMonth() + 1).padStart(2, "0");
        }
        if (!dayInput.value) {
          dayInput.value = String(new Date().getDate()).padStart(2, "0");
        } else {
          const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
          const maxDays = getDaysInMonth(y, m);
          let d = parseInt(dayInput.value, 10) || 1;
          if (d > maxDays) {
            dayInput.value = String(maxDays).padStart(2, "0");
          }
        }
        syncToNative();
      }, { passive: false });

      monthInput.addEventListener("wheel", (e) => {
        e.preventDefault();
        let m = parseInt(monthInput.value, 10);
        if (isNaN(m) || m < 1 || m > 12) {
          m = new Date().getMonth() + 1;
        }
        const step = e.deltaY < 0 ? 1 : -1;
        m = m + step;
        if (m > 12) m = 1;
        if (m < 1) m = 12;
        monthInput.value = String(m).padStart(2, "0");

        if (!yearInput.value) {
          yearInput.value = String(new Date().getFullYear());
        }
        if (!dayInput.value) {
          dayInput.value = String(new Date().getDate()).padStart(2, "0");
        } else {
          const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
          const maxDays = getDaysInMonth(y, m);
          let d = parseInt(dayInput.value, 10) || 1;
          if (d > maxDays) {
            dayInput.value = String(maxDays).padStart(2, "0");
          }
        }
        syncToNative();
      }, { passive: false });

      dayInput.addEventListener("wheel", (e) => {
        e.preventDefault();
        if (!yearInput.value) {
          yearInput.value = String(new Date().getFullYear());
        }
        if (!monthInput.value) {
          monthInput.value = String(new Date().getMonth() + 1).padStart(2, "0");
        }
        const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
        const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
        const maxDays = getDaysInMonth(y, m);

        let d = parseInt(dayInput.value, 10);
        if (isNaN(d) || d < 1 || d > maxDays) {
          d = new Date().getDate();
        }
        const step = e.deltaY < 0 ? 1 : -1;
        d = d + step;
        if (d > maxDays) d = 1;
        if (d < 1) d = maxDays;
        dayInput.value = String(d).padStart(2, "0");
        syncToNative();
      }, { passive: false });

      // 캘린더 피커 버튼 클릭 시 네이티브 날짜 선택 팝업 오픈
      if (triggerBtn) {
        triggerBtn.addEventListener("click", (e) => {
          e.preventDefault();
          if (typeof nativeInput.showPicker === "function") {
            try {
              nativeInput.showPicker();
            } catch (err) {
              nativeInput.focus();
            }
          } else {
            nativeInput.focus();
          }
        });
      }

      nativeInput.addEventListener("change", () => {
        if (!isSyncingToNative) {
          syncFromNative();
        }
      });

      // 초기 로컬 동기화
      syncFromNative();

      wrap._syncFromNative = syncFromNative;
    }

    return { setupAutoAdvancingDateInput };
  }

  window.WealthSplitDateInputController = { create };
})();
