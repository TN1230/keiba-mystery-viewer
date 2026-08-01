#!/usr/bin/env bash
# Create an on-server backup of /opt/yokuumakun_auto-x into the same place
# used by the weekly backup job (auto-detected).
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
STAMP="${YOKUMAKUN_BACKUP_STAMP:-$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)}"
LABEL="${YOKUMAKUN_BACKUP_LABEL:-manual_now}"
INCLUDE_VENV="${YOKUMAKUN_BACKUP_INCLUDE_VENV:-0}"
NAME="yokuumakun_auto-x_${LABEL}_${STAMP}"

log() { printf '%s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

[[ -d "$ROOT" ]] || die "source missing: $ROOT"

collect_cron_text() {
  {
    crontab -l 2>/dev/null || true
    sudo -n crontab -l 2>/dev/null || true
    cat /etc/cron.d/* /etc/cron.daily/* /etc/cron.weekly/* 2>/dev/null || true
    systemctl cat 'yokuum*backup*' 2>/dev/null || true
  } | tr '\t' ' '
}

discover_dest() {
  if [[ -n "${YOKUMAKUN_BACKUP_DEST:-}" ]]; then
    printf '%s\n' "$YOKUMAKUN_BACKUP_DEST"
    return 0
  fi

  local path parent
  # 1) Paths mentioned by backup-ish cron lines for yokuumakun
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -d "$path" ]]; then
      printf '%s\n' "$path"
      return 0
    fi
    parent="$(dirname "$path")"
    if [[ -d "$parent" ]]; then
      printf '%s\n' "$parent"
      return 0
    fi
  done < <(
    collect_cron_text \
      | grep -Ei 'backup|バックアップ|rsync|tar ' \
      | grep -Ei 'yokuumakun' \
      | grep -Eo '(/opt|/home/tn|/var/backups|/mnt|/media)[^[:space:]\"'\'']+' \
      | grep -Eiv 'yokuumakun_auto-x/?$|yokuumakun_auto/?$|\.(sh|py|log|service|timer)$' \
      || true
  )

  # 2) Existing backup directories that already hold auto-x snapshots
  local cand
  for cand in \
    /opt/yokuumakun_backups \
    /opt/backups/yokuumakun \
    /opt/backups \
    /var/backups/yokuumakun \
    /home/tn/backups/yokuumakun \
    /home/tn/backups \
    /home/tn/yokuumakun_backups
  do
    if [[ -d "$cand" ]] && ls -1 "$cand" 2>/dev/null | grep -Eq 'yokuumakun_auto'; then
      printf '%s\n' "$cand"
      return 0
    fi
  done

  # 3) /opt dirs named *backup* that contain yokuumakun artifacts
  while IFS= read -r cand; do
    [[ -z "$cand" ]] && continue
    if ls -1 "$cand" 2>/dev/null | grep -Eqi 'yokuumakun'; then
      printf '%s\n' "$cand"
      return 0
    fi
  done < <(ls -1d /opt/*backup* /opt/*Backup* /opt/*bak* 2>/dev/null || true)

  # 4) Sibling dated copies next to live tree
  if ls -1d /opt/yokuumakun_auto-x_* /opt/yokuumakun_auto-x-* 2>/dev/null | head -n 1 >/dev/null; then
    printf '%s\n' "/opt"
    return 0
  fi

  # 5) Known empty dests
  for cand in \
    /opt/yokuumakun_backups \
    /opt/backups/yokuumakun \
    /home/tn/backups/yokuumakun \
    /home/tn/backups
  do
    if [[ -d "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done

  # Last resort
  printf '%s\n' "/opt/yokuumakun_backups"
}

ensure_dir() {
  local d="$1"
  if [[ -d "$d" ]]; then
    return 0
  fi
  if [[ -n "${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}" ]]; then
    echo "${YOKUMAKUN_SUDO_PASS:-$YOKUMAKUN_SSH_PASS}" | sudo -S -p '' mkdir -p "$d"
    echo "${YOKUMAKUN_SUDO_PASS:-$YOKUMAKUN_SSH_PASS}" | sudo -S -p '' chown "$(id -un):$(id -gn)" "$d" || true
  elif sudo -n mkdir -p "$d" 2>/dev/null; then
    :
  else
    mkdir -p "$d"
  fi
}

DEST="$(discover_dest)"
log "source=$ROOT"
log "dest=$DEST"
log "name=$NAME"

ensure_dir "$DEST"
[[ -d "$DEST" ]] || die "cannot create dest: $DEST"
[[ -w "$DEST" ]] || die "dest not writable: $DEST (set YOKUMAKUN_SUDO_PASS or YOKUMAKUN_BACKUP_DEST)"

EXCLUDE_ARGS=(
  --exclude='.venv'
  --exclude='__pycache__'
  --exclude='.pytest_cache'
  --exclude='.git'
  --exclude='*.pyc'
  --exclude='node_modules'
)
if [[ "$INCLUDE_VENV" == "1" ]]; then
  EXCLUDE_ARGS=(--exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc')
fi

existing_tar="$(ls -1t "$DEST"/yokuumakun_auto*.tar.gz "$DEST"/yokuumakun_auto*.tgz 2>/dev/null | head -n 1 || true)"
existing_dir="$(ls -1td "$DEST"/yokuumakun_auto*/ 2>/dev/null | head -n 1 || true)"

OUT=""
if [[ -n "$existing_tar" || -z "$existing_dir" ]]; then
  OUT="$DEST/${NAME}.tar.gz"
  log "mode=tar -> $OUT"
  tar -C "$(dirname "$ROOT")" \
    "${EXCLUDE_ARGS[@]}" \
    -czf "$OUT" \
    "$(basename "$ROOT")"
else
  OUT="$DEST/$NAME"
  log "mode=dir-copy -> $OUT"
  mkdir -p "$OUT"
  if command -v rsync >/dev/null 2>&1; then
    RSYNC_EX=(--exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.git' --exclude='*.pyc' --exclude='node_modules')
    if [[ "$INCLUDE_VENV" == "1" ]]; then
      RSYNC_EX=(--exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc')
    fi
    rsync -a "${RSYNC_EX[@]}" "$ROOT"/ "$OUT"/
  else
    tar -C "$ROOT" "${EXCLUDE_ARGS[@]}" -cf - . | tar -C "$OUT" -xf -
  fi
fi

MANIFEST="$DEST/${NAME}.manifest.txt"
{
  echo "created_at_jst=$(TZ=Asia/Tokyo date -Iseconds)"
  echo "source=$ROOT"
  echo "output=$OUT"
  echo "host=$(hostname 2>/dev/null || true)"
  echo "user=$(id -un)"
  echo "include_venv=$INCLUDE_VENV"
  if [[ -f "$OUT" ]]; then
    echo "bytes=$(wc -c <"$OUT" | tr -d ' ')"
  else
    echo "bytes=$(du -sb "$OUT" 2>/dev/null | awk '{print $1}')"
  fi
  for f in .env admin_panel_api.py hwm_server_automation.py race_data.csv; do
    if [[ -e "$ROOT/$f" ]]; then
      echo "src_$f=$(stat -c '%s %Y' "$ROOT/$f" 2>/dev/null || echo present)"
    fi
  done
} >"$MANIFEST"

log "OK output=$OUT"
log "OK manifest=$MANIFEST"
ls -lah "$OUT" "$MANIFEST" || true
log "--- recent items in $DEST ---"
ls -lahdt "$DEST"/yokuumakun_auto* "$DEST"/*manifest.txt 2>/dev/null | head -n 20 || ls -lah "$DEST" | head -n 30
