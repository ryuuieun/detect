#!/bin/zsh
set -euo pipefail

BASE_DIR="/Users/ryuuieun/codex"
PYTHON_BIN="/usr/bin/python3"
CHECK_SCRIPT="${BASE_DIR}/check_ou_ist_guidelines.py"
STATE_FILE="${BASE_DIR}/.ou_ist_guidelines_state.json"
LOG_FILE="${BASE_DIR}/ou_ist_check.log"

notify_macos() {
  local title="$1"
  local message="$2"
  local esc_title="${title//\"/\\\"}"
  local esc_message="${message//\"/\\\"}"
  /usr/bin/osascript -e "display notification \"${esc_message}\" with title \"${esc_title}\"" >/dev/null 2>&1 || true
}

post_webhook_if_configured() {
  local message="$1"
  if [[ -z "${OU_IST_WEBHOOK_URL:-}" ]]; then
    return 0
  fi
  /usr/bin/curl -sS -X POST \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"${message//\"/\\\"}\"}" \
    "${OU_IST_WEBHOOK_URL}" >/dev/null || true
}

set +e
JSON_OUTPUT="$("${PYTHON_BIN}" "${CHECK_SCRIPT}" --state "${STATE_FILE}" --print-json)"
RC=$?
set -e

TARGET_YEAR="$(
  /bin/echo "${JSON_OUTPUT}" | "${PYTHON_BIN}" -c 'import json,sys; print(json.load(sys.stdin).get("target_year",""))' 2>/dev/null || true
)"

/bin/echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] exit=${RC} target_year=${TARGET_YEAR}" >> "${LOG_FILE}"
/bin/echo "${JSON_OUTPUT}" >> "${LOG_FILE}"
/bin/echo "" >> "${LOG_FILE}"

if [[ "${RC}" == "2" ]]; then
  MSG="检测到可能的新募集要項（目标年度: ${TARGET_YEAR}）"
  notify_macos "大阪大学入試情報检测" "${MSG}"
  post_webhook_if_configured "${MSG}"
elif [[ "${RC}" == "1" ]]; then
  MSG="抓取失败，请检查网络或页面结构"
  notify_macos "大阪大学入試情報检测" "${MSG}"
  post_webhook_if_configured "${MSG}"
fi

exit "${RC}"
